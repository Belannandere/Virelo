from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    plan: str = "free"
    invoices_used: int = 0
    invoices_limit: int = 10
    usage_period_start: datetime = Field(default_factory=datetime.utcnow)

    documents: list["Document"] = Relationship(back_populates="user")


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(
        default=None, foreign_key="users.id", index=True
    )
    filename: str
    filepath: str
    status: str = "uploaded"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(back_populates="documents")
    invoice: Optional["InvoiceRecord"] = Relationship(back_populates="document")


class InvoiceRecord(SQLModel, table=True):
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

    status: str
    errors: str = ""
    warnings: str = ""

    invoice: Optional[InvoiceRecord] = Relationship(back_populates="validation")