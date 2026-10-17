import sqlite3
from datetime import date, timedelta

from conftest import get_token, login


def q(app, sql, args=()):
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def post(client, url, page="/work-orders/1", **data):
    data["csrf_token"] = get_token(client, page)
    return client.post(url, data=data)


def add_schedules(app, due="2020-01-01"):
    conn = sqlite3.connect(app.config["DATABASE"])
    for equipment_id in (1, 4):
        conn.execute("INSERT INTO maintenance_schedules (equipment_id, interval_days, next_due_date) "
                     "VALUES (?, 180, ?)", (equipment_id, due))
    conn.commit()
    conn.close()


# --- visibility -------------------------------------------------------------
def test_list_requires_login(client):
    assert client.get("/work-orders/").status_code == 302


def test_list_is_scoped_to_facility(client):
    login(client, "engineer@test.com")
    assert "Test fault" in client.get("/work-orders/").get_data(as_text=True)
    other = client.__class__  # readability only
    client.post("/logout", data={"csrf_token": get_token(client, "/")})
    login(client, "techc@test.com")                     # technician at Hospital C
    assert "Test fault" not in client.get("/work-orders/").get_data(as_text=True)


def test_other_facilitys_work_order_is_404(client):
    login(client, "techc@test.com")
    assert client.get("/work-orders/1").status_code == 404


def test_county_officer_can_view_but_not_report(client):
    login(client, "officer@test.com")
    assert client.get("/work-orders/1").status_code == 200
    assert client.get("/work-orders/new").status_code == 403


# --- reporting faults -------------------------------------------------------
def test_reporter_reports_fault_and_device_status_worsens(client, app):
    login(client, "reporter@test.com")
    response = post(client, "/work-orders/new", page="/work-orders/new", asset_tag="T2",
                    description="Screen flickers", priority="high", condition="down")
    assert response.status_code == 302
    assert q(app, "SELECT status, wo_type, priority FROM work_orders WHERE description = 'Screen flickers'") \
        == [("open", "corrective", "high")]
    assert q(app, "SELECT status FROM equipment WHERE asset_tag = 'T2'") == [("non_functional",)]
    assert q(app, "SELECT COUNT(*) FROM audit_log WHERE table_name = 'work_orders' AND action = 'create'")[0][0] == 1


def test_report_never_improves_device_status(client, app):
    login(client, "reporter@test.com")
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute("UPDATE equipment SET status = 'non_functional' WHERE asset_tag = 'T2'")
    conn.commit(); conn.close()
    post(client, "/work-orders/new", page="/work-orders/new", asset_tag="T2",
         description="Minor noise", priority="low", condition="working")
    assert q(app, "SELECT status FROM equipment WHERE asset_tag = 'T2'") == [("non_functional",)]


def test_cannot_report_on_other_facilitys_device(client, app):
    login(client, "reporter@test.com")
    response = post(client, "/work-orders/new", page="/work-orders/new", asset_tag="T4",
                    description="Broken", priority="low", condition="")
    assert response.status_code == 200
    assert "No device with that asset tag" in response.get_data(as_text=True)
    assert q(app, "SELECT COUNT(*) FROM work_orders")[0][0] == 1


def test_fault_report_needs_description(client, app):
    login(client, "reporter@test.com")
    response = post(client, "/work-orders/new", page="/work-orders/new", asset_tag="T1",
                    description="  ", priority="low", condition="")
    assert "Please describe the fault" in response.get_data(as_text=True)


# --- the job workflow -----------------------------------------------------------
def test_engineer_assigns_only_technicians_of_the_same_facility(client, app):
    login(client, "engineer@test.com")
    post(client, "/work-orders/1/assign", technician_id="7")            # Hospital C technician
    assert q(app, "SELECT assigned_to FROM work_orders WHERE id = 1") == [(None,)]
    post(client, "/work-orders/1/assign", technician_id="6")
    assert q(app, "SELECT assigned_to FROM work_orders WHERE id = 1") == [(6,)]


def test_unassigned_technician_cannot_start_or_complete(client):
    login(client, "tech@test.com")
    assert post(client, "/work-orders/1/start").status_code == 403
    assert post(client, "/work-orders/1/complete", resolution_notes="x", downtime_hours="1").status_code == 403


def test_reporter_cannot_manage_jobs(client):
    login(client, "reporter@test.com")
    assert post(client, "/work-orders/1/assign", technician_id="6").status_code == 403
    assert post(client, "/work-orders/1/cancel").status_code == 403


def test_full_repair_flow(client, app):
    login(client, "engineer@test.com")
    post(client, "/work-orders/1/assign", technician_id="6")
    client.post("/logout", data={"csrf_token": get_token(client, "/")})
    login(client, "tech@test.com")
    post(client, "/work-orders/1/start")
    assert q(app, "SELECT status FROM work_orders WHERE id = 1") == [("in_progress",)]
    post(client, "/work-orders/1/complete", resolution_notes="Replaced power supply",
         downtime_hours="5.5", cost="12,000", device_status="functional")
    assert q(app, "SELECT status, downtime_hours, cost, resolution_notes FROM work_orders WHERE id = 1") \
        == [("completed", 5.5, 12000.0, "Replaced power supply")]
    assert q(app, "SELECT closed_at IS NOT NULL FROM work_orders WHERE id = 1") == [(1,)]
    assert q(app, "SELECT status FROM equipment WHERE id = 1") == [("functional",)]


def test_completion_requires_notes_and_valid_numbers(client, app):
    login(client, "engineer@test.com")
    response = post(client, "/work-orders/1/complete", resolution_notes="", downtime_hours="-3", cost="abc")
    page = response.get_data(as_text=True)
    assert "resolution notes are required" in page
    assert "Downtime (hours) must be" in page and "Cost (KSh) must be" in page
    assert q(app, "SELECT status FROM work_orders WHERE id = 1") == [("open",)]


def test_a_closed_job_cannot_be_completed_twice(client, app):
    login(client, "engineer@test.com")
    post(client, "/work-orders/1/complete", resolution_notes="Done", downtime_hours="2", cost="1000")
    post(client, "/work-orders/1/complete", resolution_notes="Again", downtime_hours="9", cost="9999")
    assert q(app, "SELECT downtime_hours, cost, resolution_notes FROM work_orders WHERE id = 1") == [(2.0, 1000.0, "Done")]


def test_engineer_can_cancel(client, app):
    login(client, "engineer@test.com")
    post(client, "/work-orders/1/cancel")
    assert q(app, "SELECT status FROM work_orders WHERE id = 1") == [("cancelled",)]


# --- preventive maintenance ---------------------------------------------------------
def test_generate_ppm_is_scoped_and_not_duplicated(client, app):
    add_schedules(app)
    login(client, "engineer@test.com")
    post(client, "/work-orders/generate-ppm", page="/work-orders/")
    assert q(app, "SELECT equipment_id FROM work_orders WHERE wo_type = 'ppm'") == [(1,)]    # not device 4
    post(client, "/work-orders/generate-ppm", page="/work-orders/")
    assert q(app, "SELECT COUNT(*) FROM work_orders WHERE wo_type = 'ppm'")[0][0] == 1


def test_completing_ppm_moves_schedule_forward(client, app):
    add_schedules(app)
    login(client, "engineer@test.com")
    post(client, "/work-orders/generate-ppm", page="/work-orders/")
    ppm_id = q(app, "SELECT id FROM work_orders WHERE wo_type = 'ppm'")[0][0]
    post(client, f"/work-orders/{ppm_id}/complete", page=f"/work-orders/{ppm_id}",
         resolution_notes="Inspected and tested", downtime_hours="1", device_status="unchanged")
    today = date.today()
    last, nxt = q(app, "SELECT last_done_date, next_due_date FROM maintenance_schedules WHERE equipment_id = 1")[0]
    assert abs((date.fromisoformat(last) - today).days) <= 1
    assert (date.fromisoformat(nxt) - date.fromisoformat(last)).days == 180


def test_technician_cannot_generate_ppm(client):
    login(client, "tech@test.com")
    assert post(client, "/work-orders/generate-ppm", page="/work-orders/").status_code == 403


# --- list filters -------------------------------------------------------------------
def test_status_filter_and_search(client):
    login(client, "admin@test.com")
    assert "Test fault" in client.get("/work-orders/?status=open").get_data(as_text=True)
    assert "No work orders match" in client.get("/work-orders/?status=completed").get_data(as_text=True)
    assert "Test fault" in client.get("/work-orders/?q=fault").get_data(as_text=True)
    assert "No work orders match" in client.get("/work-orders/?q=nothing-like-this").get_data(as_text=True)


# --- "Assigned to me" only for people who can hold jobs ---------------------------------
def test_assigned_to_me_filter_only_for_roles_that_can_hold_jobs(client):
    shown = {}
    for email in ("officer@test.com", "reporter@test.com", "tech@test.com", "engineer@test.com", "admin@test.com"):
        c = client.application.test_client()
        login(c, email)
        shown[email] = "Assigned to me" in c.get("/work-orders/").get_data(as_text=True)
    assert shown == {"officer@test.com": False, "reporter@test.com": False,
                     "tech@test.com": True, "engineer@test.com": True, "admin@test.com": True}


def test_officer_cannot_force_the_mine_filter(client):
    login(client, "officer@test.com")
    page = client.get("/work-orders/?mine=1").get_data(as_text=True)
    assert "Showing 1-1 of 1 work orders" in page          # filter ignored, officer sees the scoped list
