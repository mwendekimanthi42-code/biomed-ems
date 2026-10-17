import sqlite3
from datetime import date, timedelta

from app import metrics
from app.db import get_db
from app.reports import csv_safe
from conftest import login

TODAY = date.today()
ADMIN = {"role": "system_admin"}
OFFICER = {"role": "county_officer", "county": "Nairobi"}
ENGINEER = {"role": "facility_engineer", "facility_id": 1}


def execute(app, statements):
    conn = sqlite3.connect(app.config["DATABASE"])
    for sql, args in statements:
        conn.execute(sql, args)
    conn.commit()
    conn.close()


def query(app, fn, user):
    with app.app_context():
        return fn(get_db(), user, TODAY)


def repair(equipment_id, days_ago, downtime, cost):
    """SQL to add one completed repair job."""
    opened = f"{TODAY - timedelta(days=days_ago)} 08:00:00"
    closed = f"{TODAY - timedelta(days=days_ago)} 12:00:00"
    return ("INSERT INTO work_orders (equipment_id, wo_type, priority, status, description, reported_by, "
            "opened_at, closed_at, downtime_hours, cost) VALUES (?, 'corrective', 'medium', 'completed', "
            "'Test repair', 3, ?, ?, ?, ?)", (equipment_id, opened, closed, downtime, cost))


# --- headline numbers -----------------------------------------------------------
def test_overview_follows_scope(app):
    admin = query(app, metrics.overview, ADMIN)
    assert (admin["active"], admin["functional"], admin["non_functional"]) == (6, 5, 1)
    assert query(app, metrics.overview, OFFICER)["active"] == 3
    assert query(app, metrics.overview, ENGINEER)["active"] == 2


def test_ppm_compliance(app):
    execute(app, [
        ("INSERT INTO maintenance_schedules (equipment_id, interval_days, next_due_date) VALUES (1, 180, '2020-01-01')", ()),
        ("INSERT INTO maintenance_schedules (equipment_id, interval_days, next_due_date) VALUES (2, 180, ?)",
         ((TODAY + timedelta(days=30)).isoformat(),)),
    ])
    o = query(app, metrics.overview, ENGINEER)
    assert (o["scheduled"], o["ppm_overdue"], o["ppm_pct"]) == (2, 1, 50.0)


def test_facility_comparison_has_one_row_per_visible_facility(app):
    assert len(query(app, metrics.facility_comparison, ADMIN)) == 3
    assert len(query(app, metrics.facility_comparison, OFFICER)) == 2
    assert len(query(app, metrics.facility_comparison, ENGINEER)) == 1


def test_monthly_series_buckets_repairs_into_the_right_month(app):
    execute(app, [repair(1, 0, 10, 5000)])
    series = query(app, metrics.monthly_series, ADMIN)
    assert len(series["labels"]) == 12
    assert series["downtime"][-1] == 10.0 and series["cost"][-1] == 5000


# --- reliability ------------------------------------------------------------------
def test_reliability_math(app):
    execute(app, [("UPDATE equipment SET purchase_date = '2000-01-01'", ()),
                  repair(2, 100, 10, 0), repair(2, 90, 20, 0)])
    rows, overall = query(app, metrics.reliability, ADMIN)
    monitor = rows[0]
    # 6 devices x 730 days x 24 h = 105,120 h; 3 failures (2 completed + the open one); 30 h downtime
    assert monitor["devices"] == 6 and monitor["failures"] == 3
    assert monitor["mttr"] == 15.0
    assert monitor["mtbf"] == round((105120 - 30) / 3)
    assert monitor["availability"] == 100.0
    assert overall["failures"] == 3


def test_reliability_with_no_failures_has_no_mtbf(app):
    execute(app, [("DELETE FROM work_orders", ())])
    rows, overall = query(app, metrics.reliability, ADMIN)
    assert rows[0]["mtbf"] is None and rows[0]["mttr"] is None


# --- replacement budget -----------------------------------------------------------
def test_budget_buckets_ranking_and_scope(app):
    execute(app, [
        ("UPDATE equipment SET purchase_date = ? WHERE asset_tag = 'T2'", ((TODAY - timedelta(days=15 * 366)).isoformat(),)),
        ("UPDATE equipment SET purchase_date = ? WHERE asset_tag = 'T3'", ((TODAY - timedelta(days=int(7.5 * 365.25))).isoformat(),)),
        repair(1, 2, 5, 300000),            # T1: repairs are 67% of the 450,000 replacement cost
    ])
    candidates, summary = query(app, metrics.budget_candidates, ADMIN)
    assert [c["asset_tag"] for c in candidates] == ["T2", "T1", "T3"]
    assert summary["review_now"] == {"count": 2, "cost": 900000}
    assert summary["plan_12m"] == {"count": 1, "cost": 450000}
    mine, mine_summary = query(app, metrics.budget_candidates, ENGINEER)
    assert [c["asset_tag"] for c in mine] == ["T2", "T1"] and mine_summary["plan_12m"]["count"] == 0


def test_decommissioned_devices_are_left_out_of_the_budget(app):
    execute(app, [("UPDATE equipment SET purchase_date = '1990-01-01', status = 'decommissioned' WHERE asset_tag = 'T2'", ())])
    candidates, _ = query(app, metrics.budget_candidates, ADMIN)
    assert "T2" not in [c["asset_tag"] for c in candidates]


# --- who may open the reports ------------------------------------------------------
REPORT_URLS = ["/reports/", "/reports/audit", "/reports/audit.csv", "/reports/budget",
               "/reports/budget.csv", "/reports/reliability"]


def test_reports_are_for_engineers_officers_and_admins_only(app):
    for email, allowed in [("admin@test.com", True), ("officer@test.com", True), ("engineer@test.com", True),
                           ("tech@test.com", False), ("reporter@test.com", False)]:
        client = app.test_client()
        login(client, email)
        codes = {client.get(url).status_code for url in REPORT_URLS}
        assert codes == ({200} if allowed else {403}), email


def test_reports_need_login(client):
    assert client.get("/reports/audit").status_code == 302


def test_csv_is_scoped_and_every_download_is_audited(client, app):
    login(client, "engineer@test.com")
    response = client.get("/reports/audit.csv")
    body = response.get_data(as_text=True)
    assert response.mimetype == "text/csv"
    assert "Hospital A" in body and "Hospital C" not in body
    client.get("/reports/budget.csv")
    exports = sqlite3.connect(app.config["DATABASE"]).execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'export'").fetchone()[0]
    assert exports == 2


def test_csv_cells_cannot_run_as_formulas():
    assert csv_safe("=SUM(A1:A9)") == "'=SUM(A1:A9)"
    assert csv_safe("@cmd") == "'@cmd"
    assert csv_safe("Hospital A") == "Hospital A" and csv_safe(42) == 42


# --- the dashboard ------------------------------------------------------------------
def test_dashboard_renders_for_every_role(app):
    for email in ("admin@test.com", "officer@test.com", "engineer@test.com", "tech@test.com", "reporter@test.com"):
        client = app.test_client()
        login(client, email)
        response = client.get("/")
        assert response.status_code == 200 and "statusChart" in response.get_data(as_text=True), email


def test_facility_comparison_only_where_several_facilities_are_visible(app):
    admin, engineer = app.test_client(), app.test_client()
    login(admin, "admin@test.com")
    login(engineer, "engineer@test.com")
    assert "Facility comparison" in admin.get("/").get_data(as_text=True)
    assert "Facility comparison" not in engineer.get("/").get_data(as_text=True)


def test_reports_link_only_for_roles_that_can_open_them(app):
    for email, expected in [("engineer@test.com", True), ("officer@test.com", True), ("tech@test.com", False)]:
        client = app.test_client()
        login(client, email)
        assert ('href="/reports/"' in client.get("/").get_data(as_text=True)) is expected, email
