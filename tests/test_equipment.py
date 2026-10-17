import sqlite3
from datetime import date

from conftest import get_token, login
from app.formatting import ksh


def rows(app, sql, args=()):
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def form_data(client, **overrides):
    data = {"asset_tag": "NEW-1", "department_id": "1", "type_id": "1", "make": "Mindray",
            "model": "X100", "serial_number": "SN-1", "supplier": "Acme", "purchase_date": "2024-01-15",
            "purchase_cost": "450,000", "warranty_expiry": "2026-01-15", "status": "functional",
            "csrf_token": get_token(client, "/equipment/new")}
    data.update(overrides)
    return data


# --- who can see what ---------------------------------------------------------
def test_equipment_list_requires_login(client):
    assert client.get("/equipment/").status_code == 302


def test_engineer_sees_only_own_facility(client):
    login(client, "engineer@test.com")
    page = client.get("/equipment/").get_data(as_text=True)
    assert "T1" in page and "T2" in page
    assert "T3" not in page and "T4" not in page and "T6" not in page


def test_admin_sees_everything(client):
    login(client, "admin@test.com")
    page = client.get("/equipment/").get_data(as_text=True)
    assert all(f"T{i}" in page for i in range(1, 7))


def test_county_officer_sees_only_their_county(client):
    login(client, "officer@test.com")
    page = client.get("/equipment/").get_data(as_text=True)
    assert "T1" in page and "T3" in page
    assert "T4" not in page


def test_device_in_another_facility_returns_404(client):
    login(client, "engineer@test.com")
    assert client.get("/equipment/1").status_code == 200
    assert client.get("/equipment/4").status_code == 404      # belongs to Hospital C
    assert client.get("/equipment/4/edit").status_code == 404


def test_filter_cannot_widen_scope(client):
    login(client, "engineer@test.com")
    page = client.get("/equipment/?facility=3").get_data(as_text=True)
    assert "T4" not in page and "No devices match" in page


# --- search and filters ---------------------------------------------------------
def test_search_by_asset_tag(client):
    login(client, "admin@test.com")
    page = client.get("/equipment/?q=T5").get_data(as_text=True)
    assert "T5" in page and "T1" not in page


def test_filter_by_status(client):
    login(client, "admin@test.com")
    page = client.get("/equipment/?status=non_functional").get_data(as_text=True)
    assert "T6" in page and "T5" not in page


def test_search_treats_percent_literally(client):
    login(client, "admin@test.com")
    assert "No devices match" in client.get("/equipment/?q=%25").get_data(as_text=True)


# --- who can change things --------------------------------------------------------
def test_reporter_can_view_but_not_add(client):
    login(client, "reporter@test.com")
    assert client.get("/equipment/").status_code == 200
    assert client.get("/equipment/new").status_code == 403
    assert client.get("/equipment/1/edit").status_code == 403


def test_county_officer_is_read_only(client):
    login(client, "officer@test.com")
    assert client.get("/equipment/1").status_code == 200
    assert client.get("/equipment/new").status_code == 403


def test_engineer_registers_equipment(client, app):
    login(client, "engineer@test.com")
    response = client.post("/equipment/new", data=form_data(client))
    assert response.status_code == 302
    assert rows(app, "SELECT facility_id, purchase_cost FROM equipment WHERE asset_tag = 'NEW-1'") == [(1, 450000.0)]
    schedule = rows(app, "SELECT next_due_date FROM maintenance_schedules WHERE equipment_id = "
                         "(SELECT id FROM equipment WHERE asset_tag = 'NEW-1')")
    assert schedule == [(date.today().isoformat(),)]          # old purchase date, so due now
    assert rows(app, "SELECT action FROM audit_log WHERE action = 'create'")


def test_duplicate_asset_tag_is_rejected(client, app):
    login(client, "engineer@test.com")
    response = client.post("/equipment/new", data=form_data(client, asset_tag="T1", serial_number="X"))
    assert response.status_code == 200
    assert "already registered" in response.get_data(as_text=True)
    assert rows(app, "SELECT COUNT(*) FROM equipment") == [(6,)]


def test_engineer_cannot_use_another_facilitys_department(client, app):
    login(client, "engineer@test.com")
    response = client.post("/equipment/new", data=form_data(client, department_id="3"))
    assert response.status_code == 200
    assert rows(app, "SELECT COUNT(*) FROM equipment") == [(6,)]


def test_validation_messages(client, app):
    login(client, "engineer@test.com")
    response = client.post("/equipment/new", data=form_data(
        client, purchase_date="2999-01-01", purchase_cost="-5", asset_tag=""))
    page = response.get_data(as_text=True)
    assert "Asset tag is required" in page
    assert "cannot be in the future" in page
    assert "zero or more" in page
    assert rows(app, "SELECT COUNT(*) FROM equipment") == [(6,)]


def test_edit_records_what_changed(client, app):
    login(client, "engineer@test.com")
    token = get_token(client, "/equipment/1/edit")
    response = client.post("/equipment/1/edit", data={
        "asset_tag": "T1", "department_id": "1", "type_id": "1", "make": "Philips", "model": "",
        "serial_number": "", "supplier": "", "purchase_date": "", "purchase_cost": "",
        "warranty_expiry": "", "status": "partially_functional", "csrf_token": token})
    assert response.status_code == 302
    assert rows(app, "SELECT status, make FROM equipment WHERE id = 1") == [("partially_functional", "Philips")]
    details = rows(app, "SELECT details FROM audit_log WHERE action = 'update'")[0][0]
    assert "status" in details and "make" in details


def test_detail_page_shows_history(client):
    login(client, "engineer@test.com")
    page = client.get("/equipment/1").get_data(as_text=True)
    assert "Test fault" in page and "Work order history" in page


def test_ksh_formatting():
    assert ksh(1800000) == "KSh 1,800,000"
    assert ksh(None) == "-"
