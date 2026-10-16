"""Seed the biomedical equipment database with realistic, FICTIONAL demo data.

Run from the project root:   python seed_db.py

WARNING: this DELETES and recreates biomed.db every time it runs.
All facility names, people, and equipment records are made up for demonstration.
"""
import math
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "biomed.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

random.seed(42)  # same pattern of data on every run
TODAY = date.today()
DEMO_PASSWORD = "demo1234"  # demo accounts only, never use this in real life

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
# code, name, county, level, diligence (chance a device's PPM is on time)
FACILITIES = [
    ("RCRH", "Riverside County Referral Hospital", "Nairobi", 5, 0.90),
    ("MVRH", "Machakos Valley Referral Hospital", "Machakos", 5, 0.75),
    ("KRRH", "Kiambu Ridge County Referral Hospital", "Kiambu", 5, 0.60),
    ("EDSH", "Eastlands Sub-County Hospital", "Nairobi", 4, 0.80),
    ("MHSH", "Mwala Hills Sub-County Hospital", "Machakos", 4, 0.55),
    ("GFHC", "Greenfield Health Centre", "Nairobi", 3, 0.70),
    ("LRHC", "Limuru Road Health Centre", "Kiambu", 3, 0.50),
]

DEPARTMENTS = {
    5: ["ICU", "Theatre", "Radiology", "Maternity", "Outpatient", "Laboratory", "Renal"],
    4: ["Theatre", "Radiology", "Maternity", "Outpatient", "Laboratory"],
    3: ["Maternity", "Outpatient", "Laboratory"],
}

# code, name, risk(1-5), PPM interval days, life years, replacement cost KES,
# minimum facility level, departments where it is used, manufacturers
TYPES = [
    ("VEN", "Ventilator", 5, 90, 10, 1_800_000, 4, ["ICU", "Theatre"], ["Drager", "Mindray", "Hamilton Medical"]),
    ("MON", "Patient monitor", 4, 180, 8, 450_000, 3, ["ICU", "Theatre", "Maternity"], ["Mindray", "Philips", "Nihon Kohden", "Contec"]),
    ("DEF", "Defibrillator", 5, 90, 8, 900_000, 4, ["ICU", "Theatre", "Outpatient"], ["Philips", "Zoll", "Mindray"]),
    ("INF", "Infusion pump", 4, 180, 7, 120_000, 3, ["ICU", "Theatre", "Maternity"], ["B. Braun", "Fresenius Kabi", "Mindray"]),
    ("SYR", "Syringe pump", 4, 180, 7, 95_000, 4, ["ICU", "Maternity"], ["B. Braun", "Fresenius Kabi", "Terumo"]),
    ("ANA", "Anaesthesia machine", 5, 90, 10, 3_500_000, 4, ["Theatre"], ["Drager", "GE Healthcare", "Mindray"]),
    ("XRY", "Digital X-ray unit", 3, 180, 12, 6_000_000, 4, ["Radiology"], ["Siemens Healthineers", "GE Healthcare", "Carestream"]),
    ("USS", "Ultrasound scanner", 3, 180, 10, 2_500_000, 3, ["Radiology", "Maternity"], ["Mindray", "GE Healthcare", "Samsung Medison"]),
    ("AUT", "Autoclave", 4, 90, 12, 1_200_000, 3, ["Theatre", "Maternity"], ["Tuttnauer", "Getinge", "Steris"]),
    ("O2C", "Oxygen concentrator", 3, 180, 8, 150_000, 3, ["ICU", "Maternity", "Outpatient"], ["Philips Respironics", "Yuwell", "Inogen"]),
    ("INC", "Infant incubator", 4, 90, 10, 700_000, 3, ["Maternity"], ["Drager", "Atom", "GE Healthcare"]),
    ("HEM", "Haematology analyser", 3, 180, 8, 1_500_000, 3, ["Laboratory"], ["Sysmex", "Mindray", "Horiba"]),
    ("DIA", "Dialysis machine", 5, 90, 8, 1_900_000, 5, ["Renal"], ["Fresenius Medical Care", "Nipro", "B. Braun"]),
    ("SUC", "Suction pump", 2, 180, 8, 60_000, 3, ["ICU", "Theatre", "Maternity"], ["Medela", "Yuwell", "Laerdal"]),
    ("POX", "Pulse oximeter", 2, 365, 5, 40_000, 3, ["ICU", "Outpatient", "Maternity"], ["Contec", "Nonin", "Masimo"]),
    ("CEN", "Centrifuge", 2, 365, 10, 180_000, 3, ["Laboratory"], ["Hettich", "Eppendorf", "Thermo Fisher"]),
]

SUPPLIERS = ["MedSupply Kenya Ltd", "AfriMed Equipment", "Savannah Biomedical", "Rift Valley Medical Traders"]
FIRST = ["Wanjiru", "Otieno", "Kamau", "Achieng", "Mutua", "Njeri", "Kiprono", "Atieno", "Mwangi", "Wambui",
         "Odhiambo", "Nyambura", "Kariuki", "Akinyi", "Muthoni", "Omondi", "Chebet", "Maina", "Naliaka", "Kioko"]
LAST = ["Kimani", "Ochieng", "Mwikali", "Njoroge", "Kipchumba", "Wafula", "Mutiso", "Karanja", "Onyango",
        "Cheruiyot", "Waweru", "Musyoka", "Odera", "Kilonzo", "Barasa", "Gathoni", "Mbugua", "Nzioka", "Wekesa", "Kerubo"]

FAULTS = ["Device will not power on", "Alarm fault code displayed", "Display not working",
          "Inaccurate readings, calibration check needed", "Battery failure", "Power cable damaged",
          "Overheating during use", "Unusual noise during operation", "Leak detected", "Software error on start-up"]
FIXES = ["Replaced faulty power supply", "Replaced battery", "Recalibrated and tested OK", "Replaced damaged cable",
         "Cleaned and serviced, tested OK", "Replaced sensor", "Reinstalled software, tested OK"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def random_name():
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def at(day, hour=None):
    """A datetime on `day` at a working hour."""
    h = hour if hour is not None else random.randint(7, 16)
    return datetime(day.year, day.month, day.day, h, random.randint(0, 59))


def poisson(lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while p > limit:
        k += 1
        p *= random.random()
    return k - 1


def pick_status(ratio):
    """Older devices (ratio = age / expected life) are more likely to be faulty."""
    weights = [
        max(85 - 30 * min(ratio, 1.5), 30),          # functional
        8 + 8 * ratio,                                # partially functional
        4 + 12 * ratio,                               # non functional
        0.5 if ratio < 1 else 1 + 3 * ratio,          # decommissioned
    ]
    statuses = ["functional", "partially_functional", "non_functional", "decommissioned"]
    return random.choices(statuses, weights)[0]


def priority_for(risk):
    options = {5: ["critical", "high"], 4: ["high", "medium"], 3: ["medium", "low"], 2: ["low", "medium"]}
    return random.choice(options.get(risk, ["medium"]))


def reset_database():
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except PermissionError:
            sys.exit("Cannot delete biomed.db. Close DB Browser for SQLite and any running "
                     "Flask server, then run this script again.")


# ---------------------------------------------------------------------------
# Main seeding
# ---------------------------------------------------------------------------
def main():
    reset_database()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    pw_hash = generate_password_hash(DEMO_PASSWORD)

    def add_user(name, email, role, facility_id=None, county=None):
        cur.execute(
            "INSERT INTO users (full_name, email, password_hash, role, facility_id, county) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, pw_hash, role, facility_id, county),
        )
        return cur.lastrowid

    # --- facilities, departments, staff ------------------------------------
    facilities = []
    dept_ids = {}
    demo_logins = []
    for code, name, county, level, diligence in FACILITIES:
        cur.execute("INSERT INTO facilities (name, county, level) VALUES (?, ?, ?)", (name, county, level))
        fid = cur.lastrowid
        for dept in DEPARTMENTS[level]:
            cur.execute("INSERT INTO departments (facility_id, name) VALUES (?, ?)", (fid, dept))
            dept_ids[(fid, dept)] = cur.lastrowid
        c = code.lower()
        staff = {
            "engineer": add_user(random_name(), f"engineer.{c}@example.com", "facility_engineer", fid),
            "techs": [add_user(random_name(), f"tech{i}.{c}@example.com", "technician", fid) for i in (1, 2)],
            "reporters": [add_user(random_name(), f"nurse{i}.{c}@example.com", "reporter", fid) for i in (1, 2)],
        }
        demo_logins.append(f"engineer.{c}@example.com  ({name})")
        facilities.append({"id": fid, "code": code, "level": level, "diligence": diligence, **staff})

    admin_id = add_user("System Administrator", "admin@example.com", "system_admin")
    for county in sorted({f[2] for f in FACILITIES}):
        add_user(random_name(), f"officer.{county.lower()}@example.com", "county_officer", county=county)

    # --- equipment types ---------------------------------------------------
    type_ids = {}
    for code, name, risk, ppm, life, cost, *_ in TYPES:
        cur.execute(
            "INSERT INTO equipment_types (name, risk_score, ppm_interval_days, expected_life_years, "
            "est_replacement_cost) VALUES (?, ?, ?, ?, ?)",
            (name, risk, ppm, life, cost),
        )
        type_ids[code] = cur.lastrowid

    # --- equipment ---------------------------------------------------------
    units_per_slot = {5: (2, 6), 4: (1, 3), 3: (1, 2)}
    serial = 100000
    seq = {}
    devices = []
    for fac in facilities:
        for code, name, risk, ppm, life, cost, min_level, depts, makes in TYPES:
            if fac["level"] < min_level:
                continue
            for dept in depts:
                if (fac["id"], dept) not in dept_ids:
                    continue
                for _ in range(random.randint(*units_per_slot[fac["level"]])):
                    serial += 1
                    seq[(fac["code"], code)] = seq.get((fac["code"], code), 0) + 1
                    age_days = random.randint(90, int(life * 365 * 1.4))
                    ratio = age_days / 365 / life
                    purchase = TODAY - timedelta(days=age_days)
                    status = pick_status(ratio)
                    cur.execute(
                        "INSERT INTO equipment (asset_tag, facility_id, department_id, type_id, make, model, "
                        "serial_number, supplier, purchase_date, purchase_cost, warranty_expiry, status) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            f"{fac['code']}-{code}-{seq[(fac['code'], code)]:03d}",
                            fac["id"], dept_ids[(fac["id"], dept)], type_ids[code],
                            random.choice(makes), f"{random.choice('XMSP')}{random.randint(100, 990)}",
                            f"SN{serial}", random.choice(SUPPLIERS), purchase.isoformat(),
                            round(cost * random.uniform(0.6, 1.0), -2),
                            (purchase + timedelta(days=730)).isoformat(), status,
                        ),
                    )
                    devices.append({
                        "id": cur.lastrowid, "fac": fac, "risk": risk, "ppm": ppm, "cost": cost,
                        "purchase": purchase, "age_days": age_days, "ratio": ratio, "status": status,
                    })

    # --- maintenance schedules and PPM history ------------------------------
    wo_rows = []

    def add_wo(dev, wo_type, status, desc, reported_by, assigned_to, opened, started, closed,
               downtime, cost, notes, priority):
        wo_rows.append((
            dev["id"], wo_type, priority, status, desc, reported_by, assigned_to,
            fmt(opened), fmt(started) if started else None, fmt(closed) if closed else None,
            downtime, cost, notes,
        ))

    for dev in devices:
        if dev["status"] == "decommissioned":
            continue
        fac, interval = dev["fac"], dev["ppm"]
        last = None
        if dev["age_days"] <= interval:
            next_due = dev["purchase"] + timedelta(days=interval)   # new device, no PPM yet
        else:
            if random.random() < fac["diligence"]:
                days_ago = random.randint(0, interval)                    # on time
            else:
                days_ago = random.randint(interval + 1, int(interval * 2.2))  # overdue
            days_ago = min(days_ago, dev["age_days"] - 14)
            last = TODAY - timedelta(days=days_ago)
            next_due = last + timedelta(days=interval)
            for k in range(6):  # completed PPM history, newest first
                d = last - timedelta(days=k * interval + (random.randint(0, 7) if k else 0))
                if d < dev["purchase"] + timedelta(days=14) or d < TODAY - timedelta(days=730):
                    break
                opened = at(d)
                hours = round(random.uniform(0.5, 3.0), 1)
                add_wo(dev, "ppm", "completed", "Scheduled preventive maintenance",
                       fac["engineer"], random.choice(fac["techs"]), opened,
                       opened + timedelta(minutes=10), opened + timedelta(hours=hours), hours,
                       round(random.uniform(0, 4000), -2), "PPM completed, device tested and functional",
                       "medium" if dev["risk"] >= 4 else "low")
        cur.execute(
            "INSERT INTO maintenance_schedules (equipment_id, interval_days, last_done_date, next_due_date) "
            "VALUES (?, ?, ?, ?)",
            (dev["id"], interval, last.isoformat() if last else None, next_due.isoformat()),
        )
        if next_due < TODAY and random.random() < 0.3:   # some overdue PPMs already have an open job
            add_wo(dev, "ppm", "open", "Scheduled preventive maintenance", fac["engineer"], None,
                   at(next_due, 8), None, None, 0, 0, None, "medium" if dev["risk"] >= 4 else "low")

    # --- corrective work orders ----------------------------------------------
    for dev in devices:
        fac = dev["fac"]
        window_start = max(dev["purchase"] + timedelta(days=14), TODAY - timedelta(days=730))
        window_end = TODAY - timedelta(days=12)
        span = (window_end - window_start).days
        if span > 0:
            for _ in range(min(4, poisson(0.4 + 1.2 * min(dev["ratio"], 1.5)))):
                opened = at(window_start + timedelta(days=random.randint(0, span)))
                downtime = round(random.uniform(2, 96) * (1 + dev["ratio"]), 1)
                cost = round(min(dev["cost"] * random.uniform(0.01, 0.12) * (1 + dev["ratio"]),
                                 dev["cost"] * 0.6), -2)
                add_wo(dev, "corrective", "completed", random.choice(FAULTS),
                       random.choice(fac["reporters"]), random.choice(fac["techs"]), opened,
                       opened + timedelta(hours=min(4, downtime / 2)), opened + timedelta(hours=downtime),
                       downtime, cost, random.choice(FIXES), priority_for(dev["risk"]))
        if dev["status"] in ("partially_functional", "non_functional"):   # currently broken: open job
            opened = at(TODAY - timedelta(days=random.randint(1, 45)))
            in_progress = random.random() < 0.6
            add_wo(dev, "corrective", "in_progress" if in_progress else "open", random.choice(FAULTS),
                   random.choice(fac["reporters"]), random.choice(fac["techs"]) if in_progress else None,
                   opened, opened + timedelta(hours=6) if in_progress else None, None, 0, 0, None,
                   priority_for(dev["risk"]))

    cur.executemany(
        "INSERT INTO work_orders (equipment_id, wo_type, priority, status, description, reported_by, "
        "assigned_to, opened_at, started_at, closed_at, downtime_hours, cost, resolution_notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        wo_rows,
    )
    cur.execute("INSERT INTO audit_log (user_id, action, table_name, details) VALUES (?, 'seed', 'all', ?)",
                (admin_id, "Demo data loaded"))
    conn.commit()

    # --- summary -----------------------------------------------------------
    print("Database seeded successfully.\n")
    for table in ("facilities", "departments", "users", "equipment_types", "equipment",
                  "maintenance_schedules", "work_orders", "audit_log"):
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<24}{count:>6}")
    print(f"\nDemo password for every account: {DEMO_PASSWORD}")
    print("  admin@example.com                 (system admin, sees everything)")
    print("  officer.nairobi@example.com       (county officer; also officer.machakos / officer.kiambu)")
    print(f"  {demo_logins[0]}")
    conn.close()


if __name__ == "__main__":
    main()
