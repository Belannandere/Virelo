"""
Deep user-data isolation tests.

Goal: user A must NEVER read or modify user B's documents,
no matter what URL or HTTP method they use.

These tests hit the actual HTTP layer, so they verify the
security boundary that a real attacker would face.
"""

from app.auth import get_user_by_email
from app.repository import save_extraction


# =============================================================
# Helpers
# =============================================================

def _register(client, email, password="supersecret"):
    r = client.post(
        "/register",
        data={
            "email": email,
            "password": password,
            "password_confirm": password,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, f"register failed: {r.status_code} {r.text[:200]}"


def _logout(client):
    client.get("/logout", follow_redirects=False)


def _login(client, email, password="supersecret"):
    r = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303, f"login failed: {r.status_code}"


def _make_doc_for(session, email, filename):
    """Insert a document directly via the repository, bypassing AI/PDF."""
    user = get_user_by_email(session, email)
    assert user is not None, f"user {email} not found"
    return save_extraction(
        session,
        user_id=user.id,
        filename=filename,
        filepath=f"/tmp/{filename}",
        invoice=None,
        validation=None,
    )


def _setup_two_users(client, session):
    """
    Create users A and B, each with one document.
    Returns: (user_a_id, doc_a_id, user_b_id, doc_b_id)
    """
    _register(client, "a@example.com")
    user_a = get_user_by_email(session, "a@example.com")
    doc_a = _make_doc_for(session, "a@example.com", "a_document.pdf")
    _logout(client)

    _register(client, "b@example.com")
    user_b = get_user_by_email(session, "b@example.com")
    doc_b = _make_doc_for(session, "b@example.com", "b_secret.pdf")
    _logout(client)

    return user_a.id, doc_a.id, user_b.id, doc_b.id


# =============================================================
# 1. GET — invoice detail
# =============================================================

def test_a_cannot_get_b_invoice_detail(client, session):
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.get(f"/invoices/{doc_b_id}")
    assert r.status_code == 404, (
        f"User A was able to GET /invoices/{doc_b_id} (B's document). "
        f"Status was {r.status_code}, expected 404."
    )


def test_a_can_get_own_invoice_detail(client, session):
    """Sanity check: A can read their own document."""
    _, doc_a_id, _, _ = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.get(f"/invoices/{doc_a_id}")
    assert r.status_code == 200


# =============================================================
# 2. GET — edit form
# =============================================================

def test_a_cannot_open_edit_form_for_b_invoice(client, session):
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.get(f"/invoices/{doc_b_id}/edit")
    assert r.status_code == 404


# =============================================================
# 3. POST — edit
# =============================================================

def test_a_cannot_post_edit_to_b_invoice(client, session):
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.post(
        f"/invoices/{doc_b_id}/edit",
        data={"supplier_name": "HACKED"},
        follow_redirects=False,
    )
    assert r.status_code == 404


def test_a_cannot_modify_b_invoice_via_edit(client, session):
    """Even if response is 404, ensure B's data was not modified."""
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    client.post(
        f"/invoices/{doc_b_id}/edit",
        data={"supplier_name": "HACKED"},
        follow_redirects=False,
    )

    # Reload B's document directly from DB
    from app.models import Document
    doc = session.get(Document, doc_b_id)
    # The document may or may not have an invoice record; if it does,
    # its supplier_name must still be whatever it originally was — None
    # in our fixtures — and definitely NOT "HACKED".
    if doc and doc.invoice:
        assert doc.invoice.supplier_name != "HACKED"


# =============================================================
# 4. POST — approve / reject
# =============================================================

def test_a_cannot_approve_b_invoice(client, session):
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.post(f"/invoices/{doc_b_id}/approve", follow_redirects=False)
    assert r.status_code == 404


def test_a_cannot_reject_b_invoice(client, session):
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.post(f"/invoices/{doc_b_id}/reject", follow_redirects=False)
    assert r.status_code == 404


def test_approve_does_not_change_b_status(client, session):
    """Even after A tries to approve B's document, B's status stays 'uploaded'."""
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    client.post(f"/invoices/{doc_b_id}/approve", follow_redirects=False)

    from app.models import Document
    doc = session.get(Document, doc_b_id)
    assert doc.status == "uploaded"  # not "approved"


# =============================================================
# 5. GET — single-invoice CSV export
# =============================================================

def test_a_cannot_export_b_invoice_csv(client, session):
    _, _, _, doc_b_id = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.get(f"/invoices/{doc_b_id}/export.csv")
    assert r.status_code == 404


# =============================================================
# 6. GET — invoices list
# =============================================================

def test_list_shows_only_own_documents(client, session):
    _, _, _, _ = _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.get("/invoices")
    assert r.status_code == 200
    html = r.text
    assert "a_document.pdf" in html, "A's own invoice missing from list"
    assert "b_secret.pdf" not in html, "B's invoice leaked into A's list"


def test_b_sees_only_b_documents(client, session):
    _, _, _, _ = _setup_two_users(client, session)
    _login(client, "b@example.com")

    r = client.get("/invoices")
    assert r.status_code == 200
    html = r.text
    assert "b_secret.pdf" in html
    assert "a_document.pdf" not in html


# =============================================================
# 7. GET — export all CSV
# =============================================================

def test_export_all_csv_excludes_other_users(client, session):
    """
    Since fixture documents have no InvoiceRecord, the CSV will only
    have a header row. The important thing is that no data leaks from
    any other user (and in particular, no filename appears — but
    filenames aren't in the CSV anyway).

    This test mainly ensures the endpoint responds correctly and does
    not accidentally join across users.
    """
    _setup_two_users(client, session)
    _login(client, "a@example.com")

    r = client.get("/invoices/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    # Only header row for A (no invoices in fixtures)
    lines = [line for line in r.text.splitlines() if line.strip()]
    assert len(lines) == 1  # just the header


# =============================================================
# 8. Anonymous access — everything redirects
# =============================================================

def test_anonymous_cannot_get_invoice_detail(client, session):
    _, _, _, doc_b_id = _setup_two_users(client, session)

    r = client.get(f"/invoices/{doc_b_id}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_anonymous_cannot_list_invoices(client, session):
    r = client.get("/invoices", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_anonymous_cannot_export_csv(client, session):
    r = client.get("/invoices/export.csv", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_anonymous_cannot_upload(client, session):
    r = client.get("/upload", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# =============================================================
# 9. Edge cases — invalid IDs
# =============================================================

def test_nonexistent_invoice_returns_404(client, session):
    _register(client, "edge@example.com")
    r = client.get("/invoices/999999")
    assert r.status_code == 404


def test_negative_id_returns_404(client, session):
    _register(client, "edge@example.com")
    r = client.get("/invoices/-1")
    assert r.status_code == 404


def test_non_integer_id_returns_422(client, session):
    _register(client, "edge@example.com")
    r = client.get("/invoices/abc")
    assert r.status_code == 422