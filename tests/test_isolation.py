def _register(client, email):
    client.post(
        "/register",
        data={"email": email, "password": "supersecret", "password_confirm": "supersecret"},
        follow_redirects=False,
    )


def _create_document_for(session, email, filename="x.pdf"):
    from app.auth import get_user_by_email
    from app.repository import save_extraction

    user = get_user_by_email(session, email)
    doc = save_extraction(
        session,
        user_id=user.id,
        filename=filename,
        filepath="/tmp/x.pdf",
        invoice=None,
        validation=None,
    )
    return doc


def test_user_a_cannot_access_user_b_invoice(client, session):
    _register(client, "a@example.com")
    doc_a = _create_document_for(session, "a@example.com")
    client.get("/logout")

    _register(client, "b@example.com")
    r = client.get(f"/invoices/{doc_a.id}")
    assert r.status_code == 404


def test_list_only_shows_own_invoices(client, session):
    _register(client, "x@example.com")
    _create_document_for(session, "x@example.com", "x1.pdf")
    _create_document_for(session, "x@example.com", "x2.pdf")
    client.get("/logout")

    _register(client, "y@example.com")
    _create_document_for(session, "y@example.com", "y1.pdf")

    r = client.get("/invoices")
    assert r.status_code == 200
    assert "y1.pdf" in r.text
    assert "x1.pdf" not in r.text
    assert "x2.pdf" not in r.text