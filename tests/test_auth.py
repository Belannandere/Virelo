def test_register_and_login(client):
    r = client.post(
        "/register",
        data={"email": "alice@example.com", "password": "supersecret", "password_confirm": "supersecret"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    # Now logged in — /account works
    r = client.get("/account")
    assert r.status_code == 200
    assert "alice@example.com" in r.text

    # Logout
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"

    # After logout, /account redirects to /login
    r = client.get("/account", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_duplicate_email(client):
    payload = {"email": "bob@example.com", "password": "supersecret", "password_confirm": "supersecret"}
    r1 = client.post("/register", data=payload, follow_redirects=False)
    assert r1.status_code == 303

    client.get("/logout")

    r2 = client.post("/register", data=payload)
    assert r2.status_code == 400
    assert "already registered" in r2.text.lower()


def test_login_wrong_password(client):
    client.post(
        "/register",
        data={"email": "c@example.com", "password": "supersecret", "password_confirm": "supersecret"},
    )
    client.get("/logout")

    r = client.post("/login", data={"email": "c@example.com", "password": "wrong"})
    assert r.status_code == 401
    assert "Invalid email or password" in r.text


def test_password_mismatch(client):
    r = client.post(
        "/register",
        data={"email": "d@example.com", "password": "supersecret", "password_confirm": "different"},
    )
    assert r.status_code == 400
    assert "do not match" in r.text.lower()


def test_protected_upload_redirects_when_anonymous(client):
    r = client.get("/upload", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"