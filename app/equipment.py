"""Equipment register: search, view, add, and edit devices (scoped by role)."""
import math
import sqlite3
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .audit import log
from .auth import login_required, roles_required
from .db import get_db
from .scope import facility_clause

bp = Blueprint("equipment", __name__, url_prefix="/equipment")

PER_PAGE = 25
STATUSES = ["functional", "partially_functional", "non_functional", "decommissioned"]
EDIT_ROLES = ("system_admin", "facility_engineer")
# Rule of thumb: review a device for replacement once what you have spent
# repairing it approaches about half its replacement cost. Adjust to hospital policy.
REPAIR_REVIEW_RATIO = 0.5

SORTS = {
    "tag": "e.asset_tag",
    "type": "t.name, e.asset_tag",
    "facility": "f.name, e.asset_tag",
    "oldest": "e.purchase_date IS NULL, e.purchase_date, e.asset_tag",
    "status": "e.status, e.asset_tag",
}

FROM_SQL = """
    FROM equipment e
    JOIN facilities f ON f.id = e.facility_id
    JOIN departments d ON d.id = e.department_id
    JOIN equipment_types t ON t.id = e.type_id
    LEFT JOIN maintenance_schedules ms ON ms.equipment_id = e.id
"""


# --- helpers ----------------------------------------------------------------
def years_since(iso_date, today):
    if not iso_date:
        return None
    try:
        return round((today - date.fromisoformat(iso_date)).days / 365.25, 1)
    except ValueError:
        return None


def decorate(row, today):
    """Add computed flags (age, past end-of-life, PPM overdue) to a database row."""
    item = dict(row)
    active = item["status"] != "decommissioned"
    age = years_since(item["purchase_date"], today)
    item["age_years"] = age
    item["past_eol"] = bool(active and age is not None and age > item["expected_life_years"])
    due = item.get("next_due_date")
    item["ppm_overdue"] = bool(active and due and due < today.isoformat())
    return item


def get_equipment_or_404(equipment_id):
    """Fetch one device, but only if the user is allowed to see its facility.
    Out-of-scope devices return 404 (not 403) so their existence is not revealed."""
    clause, params = facility_clause(g.user, "e.facility_id")
    row = get_db().execute(
        "SELECT e.*, f.name AS facility_name, d.name AS department_name, "
        "       t.name AS type_name, t.risk_score, t.ppm_interval_days, "
        "       t.expected_life_years, t.est_replacement_cost, "
        "       ms.last_done_date, ms.next_due_date "
        + FROM_SQL + f"WHERE e.id = ? AND {clause}",
        [equipment_id] + params,
    ).fetchone()
    if row is None:
        abort(404)
    return row


def departments_in_scope():
    clause, params = facility_clause(g.user, "d.facility_id")
    return get_db().execute(
        "SELECT d.id, d.name, d.facility_id, f.name AS facility_name "
        "FROM departments d JOIN facilities f ON f.id = d.facility_id "
        f"WHERE {clause} ORDER BY f.name, d.name", params
    ).fetchall()


def all_types():
    return get_db().execute("SELECT id, name FROM equipment_types ORDER BY name").fetchall()


# --- list -------------------------------------------------------------------
@bp.route("/")
@login_required
def index():
    db = get_db()
    today = date.today()
    clause, params = facility_clause(g.user, "e.facility_id")
    where, args = [clause], list(params)

    q = request.args.get("q", "").strip()
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        cols = ("e.asset_tag", "e.make", "e.model", "e.serial_number", "t.name")
        where.append("(" + " OR ".join(f"{c} LIKE ? ESCAPE '\\'" for c in cols) + ")")
        args += [like] * len(cols)

    facility = request.args.get("facility", type=int)
    if facility:                      # still inside the scope clause, so it can only narrow
        where.append("e.facility_id = ?")
        args.append(facility)
    department = request.args.get("department", "").strip()
    if department:
        where.append("d.name = ?")
        args.append(department)
    type_id = request.args.get("type", type=int)
    if type_id:
        where.append("e.type_id = ?")
        args.append(type_id)
    status = request.args.get("status", "")
    if status in STATUSES:
        where.append("e.status = ?")
        args.append(status)
    overdue = request.args.get("overdue") == "1"
    if overdue:
        where.append("ms.next_due_date < ? AND e.status != 'decommissioned'")
        args.append(today.isoformat())
    eol = request.args.get("eol") == "1"
    if eol:
        where.append("e.purchase_date IS NOT NULL AND e.status != 'decommissioned' "
                     "AND (julianday(?) - julianday(e.purchase_date)) / 365.25 > t.expected_life_years")
        args.append(today.isoformat())

    sort = request.args.get("sort", "tag")
    if sort not in SORTS:
        sort = "tag"
    where_sql = " AND ".join(where)

    total = db.execute(f"SELECT COUNT(*) {FROM_SQL} WHERE {where_sql}", args).fetchone()[0]
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(1, request.args.get("page", 1, type=int)), pages)

    rows = db.execute(
        "SELECT e.id, e.asset_tag, e.make, e.model, e.status, e.purchase_date, "
        "       f.name AS facility_name, d.name AS department_name, t.name AS type_name, "
        "       t.expected_life_years, ms.next_due_date "
        f"{FROM_SQL} WHERE {where_sql} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?",
        args + [PER_PAGE, (page - 1) * PER_PAGE],
    ).fetchall()

    f_clause, f_params = facility_clause(g.user, "f.id")
    d_clause, d_params = facility_clause(g.user, "d.facility_id")
    return render_template(
        "equipment/list.html",
        items=[decorate(r, today) for r in rows],
        total=total, page=page, pages=pages, per_page=PER_PAGE,
        first=(page - 1) * PER_PAGE + 1 if total else 0,
        last=min(page * PER_PAGE, total),
        facilities=db.execute(f"SELECT f.id, f.name FROM facilities f WHERE {f_clause} ORDER BY f.name", f_params).fetchall(),
        department_names=db.execute(f"SELECT DISTINCT d.name FROM departments d WHERE {d_clause} ORDER BY d.name", d_params).fetchall(),
        types=all_types(), statuses=STATUSES,
        f={"q": q, "facility": facility, "department": department, "type": type_id,
           "status": status, "overdue": overdue, "eol": eol, "sort": sort},
        can_edit=g.user["role"] in EDIT_ROLES,
    )


# --- detail -----------------------------------------------------------------
@bp.route("/<int:equipment_id>")
@login_required
def detail(equipment_id):
    db = get_db()
    today = date.today()
    item = decorate(get_equipment_or_404(equipment_id), today)

    stats = db.execute(
        "SELECT COUNT(*) AS jobs, "
        "       COALESCE(SUM(CASE WHEN wo_type = 'corrective' THEN 1 ELSE 0 END), 0) AS corrective_jobs, "
        "       COALESCE(SUM(downtime_hours), 0) AS downtime_hours, "
        "       COALESCE(SUM(CASE WHEN wo_type = 'corrective' AND status = 'completed' "
        "                         THEN cost ELSE 0 END), 0) AS repair_cost "
        "FROM work_orders WHERE equipment_id = ? AND status != 'cancelled'",
        (equipment_id,),
    ).fetchone()
    replacement = item["est_replacement_cost"] or 0
    repair_ratio = stats["repair_cost"] / replacement if replacement else 0

    work_orders = db.execute(
        "SELECT w.*, r.full_name AS reported_by_name, a.full_name AS assigned_to_name "
        "FROM work_orders w JOIN users r ON r.id = w.reported_by "
        "LEFT JOIN users a ON a.id = w.assigned_to "
        "WHERE w.equipment_id = ? ORDER BY w.opened_at DESC LIMIT 30",
        (equipment_id,),
    ).fetchall()

    life_used = 0
    if item["age_years"] is not None and item["expected_life_years"]:
        life_used = min(100, round(item["age_years"] / item["expected_life_years"] * 100))

    warranty = None
    if item["warranty_expiry"]:
        warranty = "In warranty" if item["warranty_expiry"] >= today.isoformat() else "Warranty expired"

    return render_template(
        "equipment/detail.html", item=item, stats=stats, work_orders=work_orders,
        repair_ratio=repair_ratio, review_ratio=REPAIR_REVIEW_RATIO,
        life_used=life_used, warranty=warranty, can_edit=g.user["role"] in EDIT_ROLES,
    )


# --- add / edit -------------------------------------------------------------
def parse_form(form, departments, types):
    """Validate a submitted form. Returns (clean_values, error_messages)."""
    errors, clean = [], {}
    dept_ids = {d["id"] for d in departments}
    type_ids = {t["id"] for t in types}

    clean["asset_tag"] = form.get("asset_tag", "").strip()
    if not clean["asset_tag"]:
        errors.append("Asset tag is required.")
    elif len(clean["asset_tag"]) > 40:
        errors.append("Asset tag must be 40 characters or fewer.")

    clean["department_id"] = form.get("department_id", type=int)
    if clean["department_id"] not in dept_ids:
        errors.append("Choose a department you are allowed to manage.")
    clean["type_id"] = form.get("type_id", type=int)
    if clean["type_id"] not in type_ids:
        errors.append("Choose an equipment type.")

    for key in ("make", "model", "serial_number", "supplier"):
        clean[key] = form.get(key, "").strip() or None

    for key, name in (("purchase_date", "Purchase date"), ("warranty_expiry", "Warranty expiry")):
        raw = form.get(key, "").strip()
        clean[key] = None
        if raw:
            try:
                clean[key] = date.fromisoformat(raw).isoformat()
            except ValueError:
                errors.append(f"{name} is not a valid date.")
    if clean["purchase_date"] and clean["purchase_date"] > date.today().isoformat():
        errors.append("Purchase date cannot be in the future.")

    raw_cost = form.get("purchase_cost", "").strip().replace(",", "")
    clean["purchase_cost"] = None
    if raw_cost:
        try:
            clean["purchase_cost"] = float(raw_cost)
            if clean["purchase_cost"] < 0:
                raise ValueError
        except ValueError:
            errors.append("Purchase cost must be a number that is zero or more (KSh).")
            clean["purchase_cost"] = None

    clean["status"] = form.get("status", "functional")
    if clean["status"] not in STATUSES:
        errors.append("Choose a valid status.")
    return clean, errors


def ensure_schedule(db, equipment_id, type_id, purchase_date):
    """Give a device its PPM schedule if it does not have one yet."""
    if db.execute("SELECT 1 FROM maintenance_schedules WHERE equipment_id = ?", (equipment_id,)).fetchone():
        return
    interval = db.execute("SELECT ppm_interval_days FROM equipment_types WHERE id = ?", (type_id,)).fetchone()[0]
    start = date.fromisoformat(purchase_date) if purchase_date else date.today()
    # A device registered late that has no service record in the system is due now.
    next_due = max(start + timedelta(days=interval), date.today())
    db.execute(
        "INSERT INTO maintenance_schedules (equipment_id, interval_days, next_due_date) VALUES (?, ?, ?)",
        (equipment_id, interval, next_due.isoformat()),
    )


FIELDS = ("asset_tag", "department_id", "type_id", "make", "model", "serial_number",
          "supplier", "purchase_date", "purchase_cost", "warranty_expiry", "status")
DUPLICATE_MESSAGE = "That asset tag, or that make/model/serial number combination, is already registered."


@bp.route("/new", methods=("GET", "POST"))
@roles_required(*EDIT_ROLES)
def new():
    db = get_db()
    departments, types = departments_in_scope(), all_types()
    form = request.form if request.method == "POST" else {"status": "functional"}

    if request.method == "POST":
        clean, errors = parse_form(request.form, departments, types)
        if not errors:
            facility_id = {d["id"]: d["facility_id"] for d in departments}[clean["department_id"]]
            try:
                cur = db.execute(
                    "INSERT INTO equipment (asset_tag, facility_id, department_id, type_id, make, model, "
                    "serial_number, supplier, purchase_date, purchase_cost, warranty_expiry, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (clean["asset_tag"], facility_id, clean["department_id"], clean["type_id"],
                     clean["make"], clean["model"], clean["serial_number"], clean["supplier"],
                     clean["purchase_date"], clean["purchase_cost"], clean["warranty_expiry"], clean["status"]),
                )
                equipment_id = cur.lastrowid
                if clean["status"] != "decommissioned":
                    ensure_schedule(db, equipment_id, clean["type_id"], clean["purchase_date"])
                log(db, g.user["id"], "create", "equipment", equipment_id, f"Registered {clean['asset_tag']}")
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                errors.append(DUPLICATE_MESSAGE)
            else:
                flash(f"{clean['asset_tag']} was registered.", "success")
                return redirect(url_for("equipment.detail", equipment_id=equipment_id))
        for message in errors:
            flash(message, "danger")

    return render_template("equipment/form.html", form=form, departments=departments, types=types,
                           statuses=STATUSES, mode="new", item=None)


@bp.route("/<int:equipment_id>/edit", methods=("GET", "POST"))
@roles_required(*EDIT_ROLES)
def edit(equipment_id):
    db = get_db()
    item = get_equipment_or_404(equipment_id)
    departments, types = departments_in_scope(), all_types()
    form = request.form if request.method == "POST" else dict(item)

    if request.method == "POST":
        clean, errors = parse_form(request.form, departments, types)
        if not errors:
            facility_id = {d["id"]: d["facility_id"] for d in departments}[clean["department_id"]]
            changes = [f"{k}: {item[k]} -> {clean[k]}" for k in FIELDS if str(item[k]) != str(clean[k])]
            if not changes:
                flash("No changes to save.", "info")
                return redirect(url_for("equipment.detail", equipment_id=equipment_id))
            try:
                db.execute(
                    "UPDATE equipment SET asset_tag = ?, facility_id = ?, department_id = ?, type_id = ?, "
                    "make = ?, model = ?, serial_number = ?, supplier = ?, purchase_date = ?, "
                    "purchase_cost = ?, warranty_expiry = ?, status = ? WHERE id = ?",
                    (clean["asset_tag"], facility_id, clean["department_id"], clean["type_id"],
                     clean["make"], clean["model"], clean["serial_number"], clean["supplier"],
                     clean["purchase_date"], clean["purchase_cost"], clean["warranty_expiry"],
                     clean["status"], equipment_id),
                )
                if clean["status"] != "decommissioned":
                    ensure_schedule(db, equipment_id, clean["type_id"], clean["purchase_date"])
                log(db, g.user["id"], "update", "equipment", equipment_id, "; ".join(changes)[:500])
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                errors.append(DUPLICATE_MESSAGE)
            else:
                flash("Changes saved.", "success")
                return redirect(url_for("equipment.detail", equipment_id=equipment_id))
        for message in errors:
            flash(message, "danger")

    return render_template("equipment/form.html", form=form, departments=departments, types=types,
                           statuses=STATUSES, mode="edit", item=item)
