from conftest import get_token, login


def test_dashboard_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_success_shows_dashboard(client):
    response = login(client, "engineer@test.com")
    assert response.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert "Welcome, Engineer A" in page


def test_wrong_password_rejected(client):
    response = login(client, "engineer@test.com", password="wrong")
    assert response.status_code == 200
    assert "Invalid email or password" in response.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_unknown_email_gets_same_message(client):
    response = login(client, "nobody@test.com", password="whatever")
    assert "Invalid email or password" in response.get_data(as_text=True)


def test_inactive_user_cannot_log_in(client):
    response = login(client, "inactive@test.com")
    assert "Invalid email or password" in response.get_data(as_text=True)


def test_post_without_csrf_token_is_rejected(client):
    response = client.post("/login", data={"email": "admin@test.com", "password": "secret123"})
    assert response.status_code == 400


def test_logout_ends_session(client):
    login(client, "admin@test.com")
    token = get_token(client, "/")
    response = client.post("/logout", data={"csrf_token": token})
    assert response.status_code == 302
    assert client.get("/").status_code == 302


def test_logout_requires_post(client):
    login(client, "admin@test.com")
    assert client.get("/logout").status_code == 405


def test_redirect_to_other_site_is_blocked(client):
    response = login(client, "admin@test.com", next_url="https://evil.example.com")
    assert "evil.example.com" not in response.headers["Location"]


def test_login_events_are_audited(client, app):
    login(client, "admin@test.com")
    client.post("/logout", data={"csrf_token": get_token(client, "/")})
    login(client, "admin@test.com", password="wrong")
    import sqlite3
    conn = sqlite3.connect(app.config["DATABASE"])
    actions = [row[0] for row in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    conn.close()
    assert "login" in actions and "login_failed" in actions
