import sqlite3

import pytest

from app import DEV_SECRET, create_app
from app.formatting import eat_date, eat_time
from conftest import PASSWORD, login


# --- login lockout ----------------------------------------------------------------
def fail_logins(client, email, times):
    for _ in range(times):
        login(client, email, password="wrong-password")


def test_account_locks_after_repeated_failures(app):
    app.config["LOGIN_LOCKOUT"] = True
    client = app.test_client()
    fail_logins(client, "engineer@test.com", 5)
    response = login(client, "engineer@test.com", password=PASSWORD)      # even the right password
    assert response.status_code == 429
    assert "Too many failed attempts" in response.get_data(as_text=True)
    assert client.get("/").status_code == 302                              # still not logged in


def test_lockout_is_per_account(app):
    app.config["LOGIN_LOCKOUT"] = True
    client = app.test_client()
    fail_logins(client, "engineer@test.com", 5)
    assert login(client, "admin@test.com").status_code == 302              # other accounts unaffected


def test_unknown_emails_are_locked_the_same_way(app):
    app.config["LOGIN_LOCKOUT"] = True
    client = app.test_client()
    fail_logins(client, "nobody@test.com", 5)
    assert login(client, "nobody@test.com").status_code == 429


def test_lockout_is_off_on_the_public_demo(client):
    fail_logins(client, "engineer@test.com", 7)
    assert login(client, "engineer@test.com", password=PASSWORD).status_code == 302


def test_blocked_attempts_are_audited(app):
    app.config["LOGIN_LOCKOUT"] = True
    client = app.test_client()
    fail_logins(client, "engineer@test.com", 5)
    login(client, "engineer@test.com")
    conn = sqlite3.connect(app.config["DATABASE"])
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'login_blocked'").fetchone()[0] == 1
    conn.close()


# --- production safety ---------------------------------------------------------------
def test_production_refuses_the_default_secret_key(tmp_path):
    with pytest.raises(RuntimeError):
        create_app({"APP_ENV": "production", "SECRET_KEY": DEV_SECRET, "DATABASE": str(tmp_path / "x.db")})


def test_production_cookies_are_secure(tmp_path):
    app = create_app({"APP_ENV": "production", "SECRET_KEY": "a-real-secret", "DATABASE": str(tmp_path / "x.db")})
    assert app.config["SESSION_COOKIE_SECURE"] is True


# --- headers and health check -----------------------------------------------------------
def test_security_headers_are_present(client):
    headers = client.get("/login").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"


def test_private_pages_are_not_cached_but_static_files_are_free_to_be(client):
    login(client, "admin@test.com")
    assert client.get("/").headers["Cache-Control"] == "no-store"
    assert "no-store" not in client.get("/static/style.css").headers.get("Cache-Control", "")


def test_health_check_needs_no_login(client):
    response = client.get("/healthz")
    assert response.status_code == 200 and response.get_data(as_text=True) == "ok"


# --- Nairobi time ------------------------------------------------------------------------
def test_times_are_shown_in_nairobi_time():
    assert eat_time("2026-10-17 21:30:00") == "18 Oct 2026, 00:30"      # UTC+3 crosses midnight
    assert eat_date("2026-10-17 21:30:00") == "18 Oct 2026"
    assert eat_time(None) == "-" and eat_date("") == "-"
    assert eat_time("not a date") == "not a date"


def test_work_order_page_uses_nairobi_time(client, app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute("INSERT INTO work_orders (id, equipment_id, wo_type, description, reported_by, opened_at) "
                 "VALUES (50, 1, 'corrective', 'Late report', 3, '2026-01-05 21:30:00')")
    conn.commit()
    conn.close()
    login(client, "engineer@test.com")
    page = client.get("/work-orders/50").get_data(as_text=True)
    assert "06 Jan 2026, 00:30" in page
