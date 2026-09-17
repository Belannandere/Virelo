import json
import uuid
from contextlib import asynccontextmanager
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
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from app.ai import AIExtractionError, ai_extractor
from app.auth import (
    RequiresLogin,
    get_current_user,
    get_current_user_optional,
    get_or_create_oauth_user,
    get_user_by_email,
    hash_password,
    login_user,
    logout_user,
    verify_password,
)
from app.config import settings
from app.database import get_session, init_db
from app.export import records_to_csv
from app.export_excel import records_to_xlsx
from app.limiter import (
    release_slot,
    remaining as remaining_slots,
    reserve_slot,
)
from app.models import Document, InvoiceRecord, User
from app.oauth import oauth
from app.pdf import PDFExtractionError, ScannedPDFError, pdf_extractor
from app.repository import (
    delete_user_and_data,
    get_document_for_user,
    list_documents,
    list_invoice_records_for_user,
    save_extraction,
    set_document_status,
    update_invoice,
)
from app.schemas import Invoice, LineItem
from app.timing import timer
from app.validation import ValidationResult, validate_invoice

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Virelo", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="virelo_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=False,  # set True behind HTTPS in production
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# =============================================================
# Auth exception handler
# =============================================================

@app.exception_handler(RequiresLogin)
def requires_login_handler(request: Request, exc: RequiresLogin):
    return RedirectResponse(url="/login", status_code=303)


# =============================================================
# Public: landing, health, pricing
# =============================================================

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"title": "Virelo", "current_user": user},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/pricing", response_class=HTMLResponse)
def pricing(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        request,
        "pricing.html",
        {"title": "Pricing", "current_user": user},
    )


# =============================================================
# Auth: register / login / logout
# =============================================================

@app.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "register.html",
        {"title": "Sign up", "error": None, "current_user": None},
    )


@app.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    session: Session = Depends(get_session),
):
    email_clean = (email or "").strip().lower()

    def _fail(message: str):
        return templates.TemplateResponse(
            request,
            "register.html",
            {"title": "Sign up", "error": message, "current_user": None},
            status_code=400,
        )

    if "@" not in email_clean or len(email_clean) < 5:
        return _fail("Please enter a valid email address.")
    if not password or len(password) < 8:
        return _fail("Password must be at least 8 characters long.")
    if password != password_confirm:
        return _fail("Passwords do not match.")
    if len(password.encode("utf-8")) > 72:
        return _fail("Password is too long.")
    if get_user_by_email(session, email_clean) is not None:
        return _fail("This email is already registered.")

    user = User(email=email_clean, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)

    login_user(request, user)
    return RedirectResponse("/", status_code=303)


_LOGIN_ERRORS = {
    "oauth_failed": "OAuth authentication failed. Please try again.",
    "oauth_unavailable": "This sign-in method is not configured.",
    "oauth_link_failed": "This email is already registered. Please log in with your password.",
}


@app.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    error = _LOGIN_ERRORS.get(request.query_params.get("error") or "")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"title": "Log in", "error": error, "current_user": None},
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    session: Session = Depends(get_session),
):
    email_clean = (email or "").strip().lower()
    user = get_user_by_email(session, email_clean)

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "title": "Log in",
                "error": "Invalid email or password.",
                "current_user": None,
            },
            status_code=401,
        )

    login_user(request, user)
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


# =============================================================
# OAuth: Google
# =============================================================

def _oauth_configured(provider: str) -> bool:
    if provider == "google":
        return bool(settings.google_client_id and settings.google_client_secret)
    if provider == "github":
        return bool(settings.github_client_id and settings.github_client_secret)
    return False


@app.get("/auth/google")
async def auth_google(request: Request):
    if not _oauth_configured("google"):
        return RedirectResponse("/login?error=oauth_unavailable", status_code=303)
    redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def auth_google_callback(
    request: Request,
    session: Session = Depends(get_session),
):
    if not _oauth_configured("google"):
        return RedirectResponse("/login?error=oauth_unavailable", status_code=303)

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        return RedirectResponse("/login?error=oauth_failed", status_code=303)

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await oauth.google.parse_id_token(request, token)
        except Exception:
            userinfo = None

    if not userinfo or not userinfo.get("email") or not userinfo.get("sub"):
        return RedirectResponse("/login?error=oauth_failed", status_code=303)

    try:
        user = get_or_create_oauth_user(
            session,
            provider="google",
            provider_id=str(userinfo["sub"]),
            email=userinfo["email"],
        )
    except Exception:
        return RedirectResponse("/login?error=oauth_link_failed", status_code=303)

    login_user(request, user)
    return RedirectResponse("/", status_code=303)


# =============================================================
# OAuth: GitHub
# =============================================================

@app.get("/auth/github")
async def auth_github(request: Request):
    if not _oauth_configured("github"):
        return RedirectResponse("/login?error=oauth_unavailable", status_code=303)
    redirect_uri = str(request.url_for("auth_github_callback"))
    return await oauth.github.authorize_redirect(request, redirect_uri)


@app.get("/auth/github/callback")
async def auth_github_callback(
    request: Request,
    session: Session = Depends(get_session),
):
    if not _oauth_configured("github"):
        return RedirectResponse("/login?error=oauth_unavailable", status_code=303)

    try:
        token = await oauth.github.authorize_access_token(request)
    except Exception:
        return RedirectResponse("/login?error=oauth_failed", status_code=303)

    try:
        profile_resp = await oauth.github.get("user", token=token)
        profile = profile_resp.json()
    except Exception:
        return RedirectResponse("/login?error=oauth_failed", status_code=303)

    github_id = str(profile.get("id") or "")
    email = profile.get("email")

    if not email:
        try:
            emails_resp = await oauth.github.get("user/emails", token=token)
            for e in emails_resp.json():
                if e.get("primary") and e.get("verified"):
                    email = e["email"]
                    break
        except Exception:
            email = None

    if not email or not github_id:
        return RedirectResponse("/login?error=oauth_failed", status_code=303)

    try:
        user = get_or_create_oauth_user(
            session,
            provider="github",
            provider_id=github_id,
            email=email,
        )
    except Exception:
        return RedirectResponse("/login?error=oauth_link_failed", status_code=303)

    login_user(request, user)
    return RedirectResponse("/", status_code=303)


# =============================================================
# Account
# =============================================================

@app.get("/account", response_class=HTMLResponse)
def account(
    request: Request,
    user: User = Depends(get_current_user),
):
    used = int(user.invoices_used or 0)
    limit = int(user.invoices_limit or 0)
    remaining = max(0, limit - used)
    pct = min(100, round(used * 100 / limit)) if limit > 0 else 0

    return templates.TemplateResponse(
        request,
        "account.html",
        {
            "title": "Account",
            "current_user": user,
            "usage_used": used,
            "usage_limit": limit,
            "usage_remaining": remaining,
            "usage_pct": pct,
        },
    )


# =============================================================
# Settings: password / email / delete
# =============================================================

@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "title": "Settings",
            "current_user": user,
            "error": None,
            "success": None,
            "has_password": bool(user.password_hash),
        },
    )


@app.post("/settings/password", response_class=HTMLResponse)
def settings_password(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
):
    def _render(error=None, success=None, status_code=200):
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "title": "Settings",
                "current_user": user,
                "error": error,
                "success": success,
                "has_password": bool(user.password_hash),
            },
            status_code=status_code,
        )

    # If a password already exists, verify the current one.
    if user.password_hash:
        if not verify_password(current_password, user.password_hash):
            return _render(error="Current password is incorrect.", status_code=400)

    if not new_password or len(new_password) < 8:
        return _render(
            error="New password must be at least 8 characters long.",
            status_code=400,
        )
    if new_password != new_password_confirm:
        return _render(error="New passwords do not match.", status_code=400)
    if len(new_password.encode("utf-8")) > 72:
        return _render(error="Password is too long.", status_code=400)

    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()
    session.refresh(user)

    if current_password:
        return _render(success="Password updated.")
    return _render(
        success="Password set. You can now log in with email and password too."
    )


@app.post("/settings/email", response_class=HTMLResponse)
def settings_email(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    new_email: str = Form(""),
    current_password: str = Form(""),
):
    def _render(error=None, success=None, status_code=200):
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "title": "Settings",
                "current_user": user,
                "error": error,
                "success": success,
                "has_password": bool(user.password_hash),
            },
            status_code=status_code,
        )

    if user.password_hash:
        if not verify_password(current_password, user.password_hash):
            return _render(error="Current password is incorrect.", status_code=400)

    new_email_clean = (new_email or "").strip().lower()
    if "@" not in new_email_clean or len(new_email_clean) < 5:
        return _render(error="Please enter a valid email address.", status_code=400)
    if new_email_clean == user.email:
        return _render(success="Email is unchanged.")
    if get_user_by_email(session, new_email_clean) is not None:
        return _render(error="This email is already registered.", status_code=400)

    user.email = new_email_clean
    session.add(user)
    session.commit()
    session.refresh(user)
    return _render(success="Email updated.")


@app.post("/settings/delete")
def settings_delete(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    confirm_email: str = Form(""),
    current_password: str = Form(""),
):
    def _render(error=None, status_code=400):
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "title": "Settings",
                "current_user": user,
                "error": error,
                "success": None,
                "has_password": bool(user.password_hash),
            },
            status_code=status_code,
        )

    confirm = (confirm_email or "").strip().lower()
    if confirm != user.email.lower():
        return _render(error="Confirmation email does not match your account email.")

    if user.password_hash:
        if not verify_password(current_password, user.password_hash):
            return _render(error="Current password is incorrect.")

    user_id = user.id
    filepaths = delete_user_and_data(session, user_id)

    # Best-effort file cleanup; ignore missing files.
    for fp in filepaths:
        try:
            Path(fp).unlink(missing_ok=True)
        except OSError:
            pass

    logout_user(request)
    return RedirectResponse("/", status_code=303)


# =============================================================
# Invoices list
# =============================================================

@app.get("/invoices", response_class=HTMLResponse)
def invoices_list(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    documents = list_documents(session, user.id)
    return templates.TemplateResponse(
        request,
        "invoices.html",
        {"title": "Invoices", "documents": documents, "current_user": user},
    )


# =============================================================
# Export routes (must be BEFORE /invoices/{document_id})
# =============================================================

@app.get("/invoices/export.csv")
def export_all_csv(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    records = list_invoice_records_for_user(session, user.id)
    csv_text = records_to_csv(records)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="invoices.csv"'},
    )


@app.get("/invoices/export.xlsx")
def export_all_xlsx(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    records = list_invoice_records_for_user(session, user.id)
    content = records_to_xlsx(records)
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": 'attachment; filename="invoices.xlsx"'},
    )


# =============================================================
# Invoice detail
# =============================================================

@app.get("/invoices/{document_id}", response_class=HTMLResponse)
def invoice_detail(
    document_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    document = get_document_for_user(session, document_id, user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

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

    size_kb: float | None = None
    try:
        size_kb = round(Path(document.filepath).stat().st_size / 1024, 1)
    except OSError:
        pass

    ctx = {
        "filename": document.filename,
        "saved_as": Path(document.filepath).name,
        "size_kb": size_kb,
        "extraction": None,
        "invoice": invoice,
        "validation": validation,
        "pdf_error": None,
        "ai_error": None,
        "document_id": document.id,
        "status": document.status,
        "current_user": user,
    }
    return templates.TemplateResponse(
        request, "result.html", {**ctx, "title": "Saved invoice"}
    )


# =============================================================
# Single-invoice exports
# =============================================================

@app.get("/invoices/{document_id}/export.csv")
def export_invoice_csv(
    document_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    document = get_document_for_user(session, document_id, user.id)
    if document is None or document.invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    csv_text = records_to_csv([document.invoice])
    filename = f"invoice_{document_id}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/invoices/{document_id}/export.xlsx")
def export_invoice_xlsx(
    document_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    document = get_document_for_user(session, document_id, user.id)
    if document is None or document.invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    content = records_to_xlsx([document.invoice])
    filename = f"invoice_{document_id}.xlsx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================
# Approve / Reject
# =============================================================

@app.post("/invoices/{document_id}/approve")
def invoice_approve(
    document_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    document = get_document_for_user(session, document_id, user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    set_document_status(session, document, "approved")
    return RedirectResponse(url=f"/invoices/{document_id}", status_code=303)


@app.post("/invoices/{document_id}/reject")
def invoice_reject(
    document_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    document = get_document_for_user(session, document_id, user.id)
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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    document = get_document_for_user(session, document_id, user.id)
    if document is None or document.invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "title": "Edit invoice",
            "document_id": document_id,
            "record": document.invoice,
            "current_user": user,
        },
    )


@app.post("/invoices/{document_id}/edit")
def invoice_edit_submit(
    document_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    supplier_name: str = Form(""),
    invoice_number: str = Form(""),
    invoice_date: str = Form(""),
    due_date: str = Form(""),
    currency: str = Form(""),
    subtotal: str = Form(""),
    tax: str = Form(""),
    total: str = Form(""),
    li_description: list[str] = Form(default=[]),
    li_quantity: list[str] = Form(default=[]),
    li_unit_price: list[str] = Form(default=[]),
    li_total: list[str] = Form(default=[]),
):
    document = get_document_for_user(session, document_id, user.id)
    if document is None or document.invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

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

    # Reconstruct line items from the parallel arrays sent by the form.
    # Rows where all four fields are empty are skipped (user pressed
    # "+ Add row" but didn't fill it in).
    line_items: list[LineItem] = []
    n = max(
        len(li_description),
        len(li_quantity),
        len(li_unit_price),
        len(li_total),
    )
    for i in range(n):
        desc = li_description[i] if i < len(li_description) else ""
        qty = li_quantity[i] if i < len(li_quantity) else ""
        price = li_unit_price[i] if i < len(li_unit_price) else ""
        total_raw = li_total[i] if i < len(li_total) else ""

        desc_clean = to_str(desc)
        qty_clean = to_float(qty)
        price_clean = to_float(price)
        total_clean = to_float(total_raw)

        # Skip entirely empty rows.
        if (
            desc_clean is None
            and qty_clean is None
            and price_clean is None
            and total_clean is None
        ):
            continue

        line_items.append(
            LineItem(
                description=desc_clean,
                quantity=qty_clean,
                unit_price=price_clean,
                total=total_clean,
            )
        )

    edited = Invoice(
        supplier_name=to_str(supplier_name),
        invoice_number=to_str(invoice_number),
        invoice_date=to_str(invoice_date),
        due_date=to_str(due_date),
        currency=to_str(currency),
        subtotal=to_float(subtotal),
        tax=to_float(tax),
        total=to_float(total),
        line_items=line_items,
    )

    validation = validate_invoice(edited)

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
def upload_form(
    request: Request,
    user: User = Depends(get_current_user),
):
    limit_reached = user.invoices_used >= user.invoices_limit
    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "title": "Upload Invoice",
            "error": None,
            "current_user": user,
            "limit_reached": limit_reached,
            "remaining": remaining_slots(user),
        },
    )


@app.post("/upload", response_class=HTMLResponse)
async def upload_submit(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        reserve_slot(user, session)
    except HTTPException:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "title": "Upload Invoice",
                "error": "You've reached your monthly limit.",
                "current_user": user,
                "limit_reached": True,
                "remaining": 0,
            },
            status_code=403,
        )

    slot_reserved = True

    def _release():
        nonlocal slot_reserved
        if slot_reserved:
            release_slot(user, session)
            slot_reserved = False

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        _release()
        return _upload_error(request, user, "Please upload a PDF file.")

    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        _release()
        return _upload_error(
            request, user,
            f"File is too large. Max size is {settings.max_upload_mb} MB.",
        )
    if len(content) == 0:
        _release()
        return _upload_error(request, user, "The file is empty.")
    if not content.startswith(b"%PDF"):
        _release()
        return _upload_error(
            request, user, "This file does not look like a valid PDF."
        )

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
        "current_user": user,
    }

    with timer("pdf_extract"):
        try:
            extraction = pdf_extractor.extract_text(filepath)
            ctx["extraction"] = extraction
        except ScannedPDFError as exc:
            ctx["pdf_error"] = str(exc)
            doc = save_extraction(
                session, user_id=user.id, filename=safe_name,
                filepath=filepath, invoice=None, validation=None,
            )
            ctx["document_id"] = doc.id
            ctx["status"] = doc.status
            _release()
            return templates.TemplateResponse(
                request, "result.html", {**ctx, "title": "Scanned PDF"}
            )
        except PDFExtractionError as exc:
            ctx["pdf_error"] = f"Could not extract text: {exc}"
            doc = save_extraction(
                session, user_id=user.id, filename=safe_name,
                filepath=filepath, invoice=None, validation=None,
            )
            ctx["document_id"] = doc.id
            ctx["status"] = doc.status
            _release()
            return templates.TemplateResponse(
                request, "result.html", {**ctx, "title": "Extraction failed"}
            )

    invoice = None
    validation = None
    with timer("ai_extract"):
        try:
            invoice = await ai_extractor.extract_invoice(extraction.text)
            validation = validate_invoice(invoice)
            ctx["invoice"] = invoice
            ctx["validation"] = validation
        except AIExtractionError as exc:
            ctx["ai_error"] = str(exc)

    with timer("db_save"):
        doc = save_extraction(
            session, user_id=user.id, filename=safe_name,
            filepath=filepath, invoice=invoice, validation=validation,
        )
    ctx["document_id"] = doc.id
    ctx["status"] = doc.status

    if invoice is None:
        _release()

    return templates.TemplateResponse(
        request, "result.html", {**ctx, "title": "Extraction result"}
    )


# =============================================================
# Helpers
# =============================================================

def _upload_error(request: Request, user: User, message: str):
    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "title": "Upload Invoice",
            "error": message,
            "current_user": user,
            "limit_reached": user.invoices_used >= user.invoices_limit,
            "remaining": remaining_slots(user),
        },
        status_code=400,
    )