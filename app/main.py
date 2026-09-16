import json
import uuid
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.ai import AIExtractionError, ai_extractor
from app.config import settings
from app.database import get_session, init_db
from app.models import Document
from app.pdf import PDFExtractionError, ScannedPDFError, pdf_extractor
from app.repository import (
    list_documents,
    save_extraction,
    set_document_status,
    update_invoice,
)
from app.schemas import Invoice, LineItem
from app.validation import ValidationResult, validate_invoice
from fastapi.responses import Response
from sqlmodel import select

from app.export import records_to_csv
from app.models import InvoiceRecord

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Invoice MVP")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# =============================================================
# Home & health
# =============================================================

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"title": "Virelo"})


@app.get("/health")
def health():
    return {"status": "ok"}


# =============================================================
# Invoices list
# =============================================================

@app.get("/invoices", response_class=HTMLResponse)
def invoices_list(
    request: Request,
    session: Session = Depends(get_session),
):
    documents = list_documents(session)
    return templates.TemplateResponse(
        request,
        "invoices.html",
        {"title": "Invoices", "documents": documents},
    )

# =============================================================
# CSV export
# =============================================================

@app.get("/invoices/export.csv")
def export_all_csv(session: Session = Depends(get_session)):
    records = list(
        session.exec(
            select(InvoiceRecord).order_by(InvoiceRecord.created_at.desc())
        ).all()
    )
    csv_text = records_to_csv(records)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="invoices.csv"'
        },
    )


@app.get("/invoices/{document_id}/export.csv")
def export_invoice_csv(
    document_id: int,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if document is None or document.invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    csv_text = records_to_csv([document.invoice])
    filename = f"invoice_{document_id}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )

# =============================================================
# Invoice detail
# =============================================================

@app.get("/invoices/{document_id}", response_class=HTMLResponse)
def invoice_detail(
    document_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Восстанавливаем Pydantic-объекты из записей БД,
    # чтобы переиспользовать тот же шаблон result.html.
    invoice: Invoice | None = None
    validation: ValidationResult | None = None

    if document.invoice:
        record = document.invoice
        invoice = Invoice(
            supplier_name=record.supplier_name,
            invoice_number=record.invoice_number,
            invoice_date=record.invoice_date,
            due_date=record.due_date,
            currency=record.currency,
            subtotal=record.subtotal,
            tax=record.tax,
            total=record.total,
            line_items=[
                LineItem(
                    description=li.description,
                    quantity=li.quantity,
                    unit_price=li.unit_price,
                    total=li.total,
                )
                for li in record.line_items
            ],
        )
        if record.validation:
            validation = ValidationResult(
                status=record.validation.status,
                errors=json.loads(record.validation.errors or "[]"),
                warnings=json.loads(record.validation.warnings or "[]"),
            )

    # Размер файла берём с диска — в БД мы его не сохраняли.
    size_kb: float | None = None
    try:
        size_kb = round(Path(document.filepath).stat().st_size / 1024, 1)
    except OSError:
        pass

    ctx = {
        "filename": document.filename,
        "saved_as": Path(document.filepath).name,
        "size_kb": size_kb,
        "extraction": None,   # PDF мы уже не храним в памяти
        "invoice": invoice,
        "validation": validation,
        "pdf_error": None,
        "ai_error": None,
        "document_id": document.id,
        "status": document.status,
    }
    return templates.TemplateResponse(
        request, "result.html", {**ctx, "title": "Saved invoice"}
    )


# =============================================================
# Approve / Reject
# =============================================================

@app.post("/invoices/{document_id}/approve")
def invoice_approve(
    document_id: int,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    set_document_status(session, document, "approved")
    return RedirectResponse(url=f"/invoices/{document_id}", status_code=303)


@app.post("/invoices/{document_id}/reject")
def invoice_reject(
    document_id: int,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    set_document_status(session, document, "rejected")
    return RedirectResponse(url=f"/invoices/{document_id}", status_code=303)


# =============================================================
# Edit
# =============================================================

@app.get("/invoices/{document_id}/edit", response_class=HTMLResponse)
def invoice_edit_form(
    document_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if document is None or document.invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    record = document.invoice
    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "title": "Edit invoice",
            "document_id": document_id,
            "record": record,
        },
    )


@app.post("/invoices/{document_id}/edit")
def invoice_edit_submit(
    document_id: int,
    session: Session = Depends(get_session),
    supplier_name: str = Form(""),
    invoice_number: str = Form(""),
    invoice_date: str = Form(""),
    due_date: str = Form(""),
    currency: str = Form(""),
    subtotal: str = Form(""),
    tax: str = Form(""),
    total: str = Form(""),
):
    document = session.get(Document, document_id)
    if document is None or document.invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Формы приходят строками — превращаем в числа или None.
    def to_float(s: str) -> float | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return None

    def to_str(s: str) -> str | None:
        s = (s or "").strip()
        return s or None

    edited = Invoice(
        supplier_name=to_str(supplier_name),
        invoice_number=to_str(invoice_number),
        invoice_date=to_str(invoice_date),
        due_date=to_str(due_date),
        currency=to_str(currency),
        subtotal=to_float(subtotal),
        tax=to_float(tax),
        total=to_float(total),
        line_items=[],  # строки пока не редактируем
    )

    # Перепрогоняем валидацию на исправленных значениях.
    validation = validate_invoice(edited)

    # Исходные строки сохраняем как есть — мы их не меняли.
    for li in document.invoice.line_items:
        edited.line_items.append(
            LineItem(
                description=li.description,
                quantity=li.quantity,
                unit_price=li.unit_price,
                total=li.total,
            )
        )

    update_invoice(
        session,
        document_id=document_id,
        invoice=edited,
        validation=validation,
    )
    return RedirectResponse(url=f"/invoices/{document_id}", status_code=303)


# =============================================================
# Upload
# =============================================================

@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    return templates.TemplateResponse(
        request, "upload.html", {"title": "Upload Invoice", "error": None}
    )


@app.post("/upload", response_class=HTMLResponse)
async def upload_submit(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    # --- 1. Validation of uploaded file ---
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return _upload_error(request, "Please upload a PDF file.")

    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        return _upload_error(
            request, f"File is too large. Max size is {settings.max_upload_mb} MB."
        )
    if len(content) == 0:
        return _upload_error(request, "The file is empty.")
    if not content.startswith(b"%PDF"):
        return _upload_error(request, "This file does not look like a valid PDF.")

    # --- 2. Save file on disk ---
    safe_name = Path(file.filename).name
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    filepath = settings.upload_path / unique_name
    filepath.write_bytes(content)

    ctx: dict = {
        "filename": safe_name,
        "saved_as": unique_name,
        "size_kb": round(len(content) / 1024, 1),
        "extraction": None,
        "invoice": None,
        "validation": None,
        "pdf_error": None,
        "ai_error": None,
        "document_id": None,
        "status": None,
    }

    # --- 3. Extract text from PDF ---
    try:
        extraction = pdf_extractor.extract_text(filepath)
        ctx["extraction"] = extraction
    except ScannedPDFError as exc:
        ctx["pdf_error"] = str(exc)
        # всё равно сохраняем документ со статусом "uploaded"
        doc = save_extraction(
            session,
            filename=safe_name,
            filepath=filepath,
            invoice=None,
            validation=None,
        )
        ctx["document_id"] = doc.id
        ctx["status"] = doc.status
        return templates.TemplateResponse(
            request, "result.html", {**ctx, "title": "Scanned PDF"}
        )
    except PDFExtractionError as exc:
        ctx["pdf_error"] = f"Could not extract text: {exc}"
        doc = save_extraction(
            session,
            filename=safe_name,
            filepath=filepath,
            invoice=None,
            validation=None,
        )
        ctx["document_id"] = doc.id
        ctx["status"] = doc.status
        return templates.TemplateResponse(
            request, "result.html", {**ctx, "title": "Extraction failed"}
        )

    # --- 4. AI extraction ---
    invoice = None
    validation = None
    try:
        invoice = await ai_extractor.extract_invoice(extraction.text)
        validation = validate_invoice(invoice)
        ctx["invoice"] = invoice
        ctx["validation"] = validation
    except AIExtractionError as exc:
        ctx["ai_error"] = str(exc)

    # --- 5. Save to DB ---
    doc = save_extraction(
        session,
        filename=safe_name,
        filepath=filepath,
        invoice=invoice,
        validation=validation,
    )
    ctx["document_id"] = doc.id
    ctx["status"] = doc.status

    return templates.TemplateResponse(
        request, "result.html", {**ctx, "title": "Extraction result"}
    )


# =============================================================
# Helpers
# =============================================================

def _upload_error(request: Request, message: str):
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"title": "Upload Invoice", "error": message},
        status_code=400,
    )