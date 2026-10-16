import re
import sqlite3
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app

SCHEMA = (Path(__file__).resolve().parent.parent / "database" / "schema.sql").read_text(encoding="utf-8")
PASSWORD = "secret123"


@pytest.fixture
def app(tmp_path):
    """A fresh app with a tiny test database: 3 facilities, 6 devices, 4 users."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")

    facilities = [(1, "Hospital A", "Nairobi", 5), (2, "Clinic B", "Nairobi", 3),
                  (3, "Hospital C", "Machakos", 5)]
    for fid, name, county, level in facilities:
        conn.execute("INSERT INTO facilities (id, name, county, level) VALUES (?, ?, ?, ?)",
                     (fid, name, county, level))
        conn.execute("INSERT INTO departments (id, facility_id, name) VALUES (?, ?, 'ICU')", (fid, fid))
    conn.execute("INSERT INTO equipment_types (id, name, risk_score, ppm_interval_days, "
                 "expected_life_years, est_replacement_cost) VALUES (1, 'Monitor', 4, 180, 8, 450000)")
    for i, fid in enumerate([1, 1, 2, 3, 3, 3], start=1):
        conn.execute("INSERT INTO equipment (asset_tag, facility_id, department_id, type_id) "
                     "VALUES (?, ?, ?, 1)", (f"T{i}", fid, fid))

    pw = generate_password_hash(PASSWORD)
    users = [
        (1, "Admin", "admin@test.com", "system_admin", None, None, 1),
        (2, "Officer", "officer@test.com", "county_officer", None, "Nairobi", 1),
        (3, "Engineer A", "engineer@test.com", "facility_engineer", 1, None, 1),
        (4, "Inactive", "inactive@test.com", "technician", 1, None, 0),
    ]
    for uid, name, email, role, fid, county, active in users:
        conn.execute("INSERT INTO users (id, full_name, email, password_hash, role, facility_id, "
                     "county, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (uid, name, email, pw, role, fid, county, active))
    conn.execute("INSERT INTO work_orders (equipment_id, wo_type, description, reported_by) "
                 "VALUES (1, 'corrective', 'Test fault', 3)")
    conn.commit()
    conn.close()

    return create_app({"TESTING": True, "DATABASE": str(db_path), "SECRET_KEY": "test-key"})


@pytest.fixture
def client(app):
    return app.test_client()


def get_token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def login(client, email, password=PASSWORD, next_url=None):
    url = "/login" + (f"?next={next_url}" if next_url else "")
    token = get_token(client, url)
    return client.post(url, data={"email": email, "password": password, "csrf_token": token})
