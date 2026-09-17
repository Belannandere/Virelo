import json
from pathlib import Path

from sqlmodel import Session, select

from app.models import Document, InvoiceRecord, LineItemRecord, ValidationRecord
from app.schemas import Invoice
from app.validation import ValidationResult


def save_extraction(
    session: Session,
    *,
    filename: str,
    filepath: Path,
    invoice: Invoice | None,
    validation: ValidationResult | None,
) -> Document:
    """Сохраняет документ, инвойс, строки и результат валидации в БД."""
    document = Document(
        filename=filename,
        filepath=str(filepath),
        status="extracted" if invoice else "uploaded",
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    if invoice is None:
        return document

    record = InvoiceRecord(
        document_id=document.id,
        supplier_name=invoice.supplier_name,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    for li in invoice.line_items:
        session.add(
            LineItemRecord(
                invoice_id=record.id,
                description=li.description,
                quantity=li.quantity,
                unit_price=li.unit_price,
                total=li.total,
            )
        )
    session.commit()

    if validation is not None:
        session.add(
            ValidationRecord(
                invoice_id=record.id,
                status=validation.status,
                errors=json.dumps(validation.errors),
                warnings=json.dumps(validation.warnings),
            )
        )
        session.commit()

    return document


def list_documents(session: Session) -> list[Document]:
    statement = select(Document).order_by(Document.created_at.desc())
    return list(session.exec(statement).all())


def get_document(session: Session, document_id: int) -> Document | None:
    return session.get(Document, document_id)

def set_document_status(
    session: Session, document: Document, status: str
) -> Document:
    document.status = status
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def update_invoice(
    session: Session,
    *,
    document_id: int,
    invoice: Invoice,
    validation: ValidationResult,
) -> None:
    """Обновляет поля инвойса, перезаписывает line_items и validation."""
    record = session.exec(
        select(InvoiceRecord).where(InvoiceRecord.document_id == document_id)
    ).first()
    if record is None:
        raise ValueError(f"No invoice record for document {document_id}")


    record.supplier_name = invoice.supplier_name
    record.invoice_number = invoice.invoice_number
    record.invoice_date = invoice.invoice_date
    record.due_date = invoice.due_date
    record.currency = invoice.currency
    record.subtotal = invoice.subtotal
    record.tax = invoice.tax
    record.total = invoice.total
    session.add(record)
    session.commit()


    old_items = session.exec(
        select(LineItemRecord).where(LineItemRecord.invoice_id == record.id)
    ).all()
    for li in old_items:
        session.delete(li)
    session.commit()

    for li in invoice.line_items:
        session.add(
            LineItemRecord(
                invoice_id=record.id,
                description=li.description,
                quantity=li.quantity,
                unit_price=li.unit_price,
                total=li.total,
            )
        )
    session.commit()


    old_val = session.exec(
        select(ValidationRecord).where(ValidationRecord.invoice_id == record.id)
    ).first()
    if old_val is not None:
        session.delete(old_val)
        session.commit()

    session.add(
        ValidationRecord(
            invoice_id=record.id,
            status=validation.status,
            errors=json.dumps(validation.errors),
            warnings=json.dumps(validation.warnings),
        )
    )
    session.commit()