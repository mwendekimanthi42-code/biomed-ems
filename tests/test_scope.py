from app.db import get_db
from app.scope import facility_clause

ADMIN = {"role": "system_admin"}
OFFICER_NAIROBI = {"role": "county_officer", "county": "Nairobi"}
ENGINEER_A = {"role": "facility_engineer", "facility_id": 1}
ENGINEER_C = {"role": "facility_engineer", "facility_id": 3}


def equipment_count(app, user):
    with app.app_context():
        clause, params = facility_clause(user, "e.facility_id")
        return get_db().execute(f"SELECT COUNT(*) FROM equipment e WHERE {clause}", params).fetchone()[0]


def facility_count(app, user):
    with app.app_context():
        clause, params = facility_clause(user, "f.id")
        return get_db().execute(f"SELECT COUNT(*) FROM facilities f WHERE {clause}", params).fetchone()[0]


def test_system_admin_sees_everything(app):
    assert equipment_count(app, ADMIN) == 6
    assert facility_count(app, ADMIN) == 3


def test_county_officer_sees_only_their_county(app):
    assert equipment_count(app, OFFICER_NAIROBI) == 3     # Hospital A (2) + Clinic B (1)
    assert facility_count(app, OFFICER_NAIROBI) == 2


def test_facility_staff_see_only_their_facility(app):
    assert equipment_count(app, ENGINEER_A) == 2
    assert equipment_count(app, ENGINEER_C) == 3
    assert facility_count(app, ENGINEER_A) == 1
