from app.auth import get_user_by_email
from app.models import Document, InvoiceRecord, LineItemRecord
from app.repository import save_extraction
from app.schemas import Invoice, LineItem
from app.validation import validate_invoice


def _register(client, email="li@example.com", password="supersecret"):
    client.post(
        "/register",
        data={
            "email": email,
            "password": password,
            "password_confirm": password,
        },
        follow_redirects=False,
    )


def _make_doc_with_invoice(session, email, invoice: Invoice):
    user = get_user_by_email(session, email)
    doc = save_extraction(
        session,
        user_id=user.id,
        filename="li.pdf",
        filepath="/tmp/li.pdf",
        invoice=invoice,
        validation=validate_invoice(invoice),
    )
    return doc


def _seed_invoice() -> Invoice:
    return Invoice(
        supplier_name="Acme",
        invoice_number="INV-1",
        invoice_date="2026-01-01",
        due_date="2026-02-01",
        currency="EUR",
        subtotal=100.0,
        tax=20.0,
        total=120.0,
        line_items=[
            LineItem(description="Widget", quantity=2, unit_price=50.0, total=100.0),
        ],
    )


def test_edit_updates_line_items(client, session):
    _register(client)
    doc = _make_doc_with_invoice(session, "li@example.com", _seed_invoice())

    r = client.post(
        f"/invoices/{doc.id}/edit",
        data={
            "supplier_name": "Acme",
            "invoice_number": "INV-1",
            "invoice_date": "2026-01-01",
            "due_date": "2026-02-01",
            "currency": "EUR",
            "subtotal": "100",
            "tax": "20",
            "total": "120",
            # Two line items now
            "li_description": ["Widget", "Gadget"],
            "li_quantity": ["2", "1"],
            "li_unit_price": ["50", "25"],
            "li_total": ["100", "25"],
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Reload invoice from DB
    session.expire_all()
    inv = session.exec(
        InvoiceRecord.__table__.select().where(InvoiceRecord.document_id == doc.id)
    ).first()
    items = session.exec(
        LineItemRecord.__table__.select().where(
            LineItemRecord.invoice_id == inv.id
        )
    ).all()
    assert len(items) == 2
    descriptions = sorted(row.description for row in items)
    assert descriptions == ["Gadget", "Widget"]


def test_edit_can_delete_all_line_items(client, session):
    _register(client)
    doc = _make_doc_with_invoice(session, "li@example.com", _seed_invoice())

    # Send no line item fields at all → all deleted
    r = client.post(
        f"/invoices/{doc.id}/edit",
        data={
            "supplier_name": "Acme",
            "invoice_number": "INV-1",
            "subtotal": "0",
            "tax": "0",
            "total": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    session.expire_all()
    inv = session.exec(
        InvoiceRecord.__table__.select().where(InvoiceRecord.document_id == doc.id)
    ).first()
    items = session.exec(
        LineItemRecord.__table__.select().where(
            LineItemRecord.invoice_id == inv.id
        )
    ).all()
    assert len(items) == 0


def test_edit_skips_fully_empty_rows(client, session):
    _register(client)
    doc = _make_doc_with_invoice(session, "li@example.com", _seed_invoice())

    r = client.post(
        f"/invoices/{doc.id}/edit",
        data={
            "supplier_name": "Acme",
            "invoice_number": "INV-1",
            "subtotal": "100",
            "tax": "20",
            "total": "120",
            # One real row, one empty row
            "li_description": ["Widget", ""],
            "li_quantity": ["2", ""],
            "li_unit_price": ["50", ""],
            "li_total": ["100", ""],
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    session.expire_all()
    inv = session.exec(
        InvoiceRecord.__table__.select().where(InvoiceRecord.document_id == doc.id)
    ).first()
    items = session.exec(
        LineItemRecord.__table__.select().where(
            LineItemRecord.invoice_id == inv.id
        )
    ).all()
    assert len(items) == 1
    assert items[0].description == "Widget"


def test_edit_triggers_revalidation(client, session):
    """After editing line items, validation should reflect the new sum."""
    _register(client)
    doc = _make_doc_with_invoice(session, "li@example.com", _seed_invoice())

    # Now line items sum to 500 but subtotal still 100 → warning expected
    r = client.post(
        f"/invoices/{doc.id}/edit",
        data={
            "supplier_name": "Acme",
            "invoice_number": "INV-1",
            "subtotal": "100",
            "tax": "20",
            "total": "120",
            "li_description": ["Big ticket"],
            "li_quantity": ["1"],
            "li_unit_price": ["500"],
            "li_total": ["500"],
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r2 = client.get(f"/invoices/{doc.id}")
    assert "Sum of line items" in r2.text


def test_edit_does_not_allow_modifying_other_user(client, session):
    _register(client, "owner@example.com")
    doc = _make_doc_with_invoice(session, "owner@example.com", _seed_invoice())
    client.get("/logout", follow_redirects=False)

    _register(client, "intruder@example.com")
    r = client.post(
        f"/invoices/{doc.id}/edit",
        data={
            "supplier_name": "HACKED",
            "li_description": ["Hack"],
            "li_quantity": ["1"],
            "li_unit_price": ["1"],
            "li_total": ["1"],
        },
        follow_redirects=False,
    )
    assert r.status_code == 404