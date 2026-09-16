from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    filepath: str
    status: str = "uploaded"          # uploaded | extracted | approved | rejected
    created_at: datetime = Field(default_factory=datetime.utcnow)

    invoice: Optional["InvoiceRecord"] = Relationship(back_populates="document")


class InvoiceRecord(SQLModel, table=True):
    """Таблица с полями инвойса. Название InvoiceRecord, чтобы не путать с Pydantic-схемой Invoice."""

    __tablename__ = "invoices"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id")

    supplier_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    document: Optional[Document] = Relationship(back_populates="invoice")
    line_items: list["LineItemRecord"] = Relationship(back_populates="invoice")
    validation: Optional["ValidationRecord"] = Relationship(back_populates="invoice")


class LineItemRecord(SQLModel, table=True):
    __tablename__ = "line_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoices.id")

    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None

    invoice: Optional[InvoiceRecord] = Relationship(back_populates="line_items")


class ValidationRecord(SQLModel, table=True):
    __tablename__ = "validation_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoices.id", unique=True)

    status: str                         # passed | review
    errors: str = ""                    # JSON-строка со списком
    warnings: str = ""                  # JSON-строка со списком

    invoice: Optional[InvoiceRecord] = Relationship(back_populates="validation")