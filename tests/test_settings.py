from app.auth import get_user_by_email
from app.models import User


def _register(client, email="s@example.com", password="supersecret"):
    client.post(
        "/register",
        data={
            "email": email,
            "password": password,
            "password_confirm": password,
        },
        follow_redirects=False,
    )


def test_change_password_wrong_current(client, session):
    _register(client)
    r = client.post(
        "/settings/password",
        data={
            "current_password": "wrongpass",
            "new_password": "newsecure1",
            "new_password_confirm": "newsecure1",
        },
    )
    assert r.status_code == 400
    assert "Current password is incorrect" in r.text


def test_change_password_success(client, session):
    _register(client)
    r = client.post(
        "/settings/password",
        data={
            "current_password": "supersecret",
            "new_password": "newsecure1",
            "new_password_confirm": "newsecure1",
        },
    )
    assert r.status_code == 200
    assert "Password updated" in r.text

    # Old password no longer works
    client.get("/logout", follow_redirects=False)
    r = client.post(
        "/login",
        data={"email": "s@example.com", "password": "supersecret"},
    )
    assert r.status_code == 401

    # New password works
    r = client.post(
        "/login",
        data={"email": "s@example.com", "password": "newsecure1"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_set_password_for_oauth_user(client, session):
    # Register via normal flow so we get a valid session cookie.
    _register(client, "oauth@example.com")

    # Simulate an OAuth-only account: null out the password hash.
    u = get_user_by_email(session, "oauth@example.com")
    assert u is not None
    u.password_hash = None
    session.add(u)
    session.commit()

    # Setting a password should not require the "current password".
    r = client.post(
        "/settings/password",
        data={
            "new_password": "brandnewpw1",
            "new_password_confirm": "brandnewpw1",
        },
    )
    assert r.status_code == 200
    assert "Password set" in r.text

    # New password works for login.
    client.get("/logout", follow_redirects=False)
    r = client.post(
        "/login",
        data={"email": "oauth@example.com", "password": "brandnewpw1"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_change_email(client, session):
    _register(client, "old@example.com")
    r = client.post(
        "/settings/email",
        data={
            "new_email": "new@example.com",
            "current_password": "supersecret",
        },
    )
    assert r.status_code == 200
    assert "Email updated" in r.text

    u = get_user_by_email(session, "new@example.com")
    assert u is not None


def test_change_email_taken(client, session):
    _register(client, "first@example.com")
    client.get("/logout", follow_redirects=False)
    _register(client, "second@example.com")

    r = client.post(
        "/settings/email",
        data={
            "new_email": "first@example.com",
            "current_password": "supersecret",
        },
    )
    assert r.status_code == 400
    assert "already registered" in r.text


def test_delete_account(client, session):
    _register(client, "gone@example.com")
    u = get_user_by_email(session, "gone@example.com")
    assert u is not None

    r = client.post(
        "/settings/delete",
        data={
            "confirm_email": "gone@example.com",
            "current_password": "supersecret",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    # User no longer exists
    assert get_user_by_email(session, "gone@example.com") is None


def test_delete_account_wrong_confirm(client, session):
    _register(client, "keep@example.com")
    r = client.post(
        "/settings/delete",
        data={
            "confirm_email": "wrong@example.com",
            "current_password": "supersecret",
        },
    )
    assert r.status_code == 400
    assert "does not match" in r.text

    # Still exists
    assert get_user_by_email(session, "keep@example.com") is not None