from datetime import datetime, timedelta

from app.auth import get_user_by_email


def _register(client, email="lim@example.com"):
    client.post(
        "/register",
        data={"email": email, "password": "supersecret", "password_confirm": "supersecret"},
        follow_redirects=False,
    )


def test_limit_resets_for_new_month(client, session):
    _register(client)
    user = get_user_by_email(session, "lim@example.com")
    user.invoices_used = 10
    user.usage_period_start = datetime.utcnow() - timedelta(days=60)
    session.add(user)
    session.commit()
    session.refresh(user)

    # Simulate "check" path by visiting /account then re-reading
    client.get("/account")
    session.refresh(user)

    # Since the period rolled over, usage should be reset to 0
    assert user.invoices_used == 0


def test_limit_blocks_11th_slot(client, session):
    _register(client, "block@example.com")
    user = get_user_by_email(session, "block@example.com")
    user.invoices_used = 10
    user.invoices_limit = 10
    user.usage_period_start = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)

    # Uploading anything should be rejected by the reserve step,
    # regardless of the file being valid.
    r = client.post(
        "/upload",
        files={"file": ("bad.txt", b"not a pdf", "application/pdf")},
    )
    assert r.status_code == 403
    assert "limit" in r.text.lower()