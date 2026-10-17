"""Work orders: report faults, assign, work on, complete and cancel jobs."""
import math
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .audit import log
from .auth import login_required, roles_required
from .db import get_db
from .scope import facility_clause

bp = Blueprint("workorders", __name__, url_prefix="/work-orders")

PER_PAGE = 25
MANAGE_ROLES = ("system_admin", "facility_engineer")
REPORT_ROLES = ("system_admin", "facility_engineer", "technician", "reporter")
PRIORITIES = ["low", "medium", "high", "critical"]
WO_STATUSES = ["open", "in_progress", "completed", "cancelled"]
SEVERITY = {"functional": 0, "partially_functional": 1, "non_functional": 2}
CONDITIONS = {"working": "functional", "partial": "partially_functional", "down": "non_functional"}
JOB_HOLDER_ROLES = ("system_admin", "facility_engineer", "technician")   # roles that can be assigned jobs
PPM_LOOKAHEAD_DAYS = 7

FROM_SQL = """
    FROM work_orders w
    JOIN equipment e ON e.id = w.equipment_id
    JOIN facilities f ON f.id = e.facility_id
    JOIN equipment_types t ON t.id = e.type_id
    JOIN users r ON r.id = w.reported_by
    LEFT JOIN users a ON a.id = w.assigned_to
"""


# --- helpers ----------------------------------------------------------------
def now_utc():
    """Times are stored in UTC, matching SQLite's CURRENT_TIMESTAMP."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def is_manager():
    return g.user["role"] in MANAGE_ROLES


def can_work(wo):
    """Managers can work any job; a technician only the jobs assigned to them."""
    return is_manager() or (g.user["role"] == "technician" and wo["assigned_to"] == g.user["id"])


def get_wo_or_404(wo_id):
    clause, params = facility_clause(g.user, "e.facility_id")
    row = get_db().execute(
        "SELECT w.*, e.asset_tag, e.facility_id, e.status AS equipment_status, e.type_id, "
        "       f.name AS facility_name, t.name AS type_name, t.ppm_interval_days, "
        "       r.full_name AS reported_by_name, a.full_name AS assigned_to_name "
        + FROM_SQL + f"WHERE w.id = ? AND {clause}",
        [wo_id] + params,
    ).fetchone()
    if row is None:
        abort(404)
    return row


def find_equipment(asset_tag):
    """Look up a device by asset tag, but only inside the user's scope."""
    clause, params = facility_clause(g.user, "e.facility_id")
    return get_db().execute(
        "SELECT e.id, e.asset_tag, e.status, e.facility_id, t.name AS type_name "
        "FROM equipment e JOIN equipment_types t ON t.id = e.type_id "
        f"WHERE e.asset_tag = ? AND {clause}",
        [asset_tag] + params,
    ).fetchone()


def parse_number(raw, label, errors, required=True):
    raw = (raw or "").strip().replace(",", "")
    if not raw:
        if required:
            errors.append(f"{label} is required.")
        return 0.0
    try:
        value = float(raw)
        if value < 0:
            raise ValueError
        return value
    except ValueError:
        errors.append(f"{label} must be a number that is zero or more.")
        return 0.0


def set_equipment_status(db, equipment_id, new_status, reason):
    """Change a device's status and record it in the audit log."""
    old = db.execute("SELECT status FROM equipment WHERE id = ?", (equipment_id,)).fetchone()[0]
    if old == "decommissioned" or old == new_status:
        return
    db.execute("UPDATE equipment SET status = ? WHERE id = ?", (new_status, equipment_id))
    log(db, g.user["id"], "update", "equipment", equipment_id, f"status: {old} -> {new_status} ({reason})")


# --- list -------------------------------------------------------------------
@bp.route("/")
@login_required
def index():
    db = get_db()
    clause, params = facility_clause(g.user, "e.facility_id")
    where, args = [clause], list(params)

    status = request.args.get("status", "")
    if status == "active":
        where.append("w.status IN ('open', 'in_progress')")
    elif status in WO_STATUSES:
        where.append("w.status = ?")
        args.append(status)
    wo_type = request.args.get("type", "")
    if wo_type in ("ppm", "corrective"):
        where.append("w.wo_type = ?")
        args.append(wo_type)
    priority = request.args.get("priority", "")
    if priority in PRIORITIES:
        where.append("w.priority = ?")
        args.append(priority)
    facility = request.args.get("facility", type=int)
    if facility:
        where.append("e.facility_id = ?")
        args.append(facility)
    can_have_jobs = g.user["role"] in JOB_HOLDER_ROLES
    mine = can_have_jobs and request.args.get("mine") == "1"
    if mine:
        where.append("w.assigned_to = ?")
        args.append(g.user["id"])
    q = request.args.get("q", "").strip()
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(e.asset_tag LIKE ? ESCAPE '\\' OR w.description LIKE ? ESCAPE '\\')")
        args += [like, like]
    where_sql = " AND ".join(where)

    total = db.execute(f"SELECT COUNT(*) {FROM_SQL} WHERE {where_sql}", args).fetchone()[0]
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(1, request.args.get("page", 1, type=int)), pages)

    rows = db.execute(
        "SELECT w.id, w.wo_type, w.priority, w.status, w.description, w.opened_at, "
        "       e.asset_tag, f.name AS facility_name, a.full_name AS assigned_to_name "
        f"{FROM_SQL} WHERE {where_sql} "
        "ORDER BY CASE w.status WHEN 'in_progress' THEN 0 WHEN 'open' THEN 1 ELSE 2 END, "
        "         CASE WHEN w.status IN ('open', 'in_progress') "
        "              THEN CASE w.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END "
        "              ELSE 4 END, w.opened_at DESC LIMIT ? OFFSET ?",
        args + [PER_PAGE, (page - 1) * PER_PAGE],
    ).fetchall()

    counts = {r["status"]: r["n"] for r in db.execute(
        f"SELECT w.status, COUNT(*) AS n {FROM_SQL} WHERE {clause} GROUP BY w.status", params)}
    f_clause, f_params = facility_clause(g.user, "f.id")
    return render_template(
        "workorders/list.html", items=rows, total=total, page=page, pages=pages,
        first=(page - 1) * PER_PAGE + 1 if total else 0, last=min(page * PER_PAGE, total),
        counts=counts, priorities=PRIORITIES,
        facilities=db.execute(f"SELECT f.id, f.name FROM facilities f WHERE {f_clause} ORDER BY f.name", f_params).fetchall(),
        f={"status": status, "type": wo_type, "priority": priority, "facility": facility, "mine": mine, "q": q},
        can_manage=is_manager(), can_report=g.user["role"] in REPORT_ROLES,
        can_have_jobs=can_have_jobs,
    )


# --- detail -----------------------------------------------------------------
def show_detail(wo, form=None):
    db = get_db()
    opened = datetime.strptime(wo["opened_at"], "%Y-%m-%d %H:%M:%S")
    elapsed = round((now_utc() - opened).total_seconds() / 3600, 1)
    active = wo["status"] in ("open", "in_progress")
    technicians = []
    if is_manager() and active:
        technicians = db.execute(
            "SELECT id, full_name FROM users WHERE role = 'technician' AND is_active = 1 "
            "AND facility_id = ? ORDER BY full_name", (wo["facility_id"],)).fetchall()
    defaults = form or {
        "downtime_hours": 1.0 if wo["wo_type"] == "ppm" else max(elapsed, 0),
        "cost": 0,
        "device_status": "unchanged" if wo["wo_type"] == "ppm" else "functional",
    }
    return render_template("workorders/detail.html", wo=wo, active=active, technicians=technicians,
                           can_work=can_work(wo), can_manage=is_manager(), form=defaults)


@bp.route("/<int:wo_id>")
@login_required
def detail(wo_id):
    return show_detail(get_wo_or_404(wo_id))


# --- report a fault ---------------------------------------------------------
@bp.route("/new", methods=("GET", "POST"))
@roles_required(*REPORT_ROLES)
def new():
    db = get_db()
    form = request.form if request.method == "POST" else {"priority": "medium", "condition": ""}
    if request.method == "GET" and request.args.get("equipment_id", type=int):
        clause, params = facility_clause(g.user, "e.facility_id")
        row = db.execute(f"SELECT asset_tag FROM equipment e WHERE e.id = ? AND {clause}",
                         [request.args.get("equipment_id", type=int)] + params).fetchone()
        if row:
            form = {"asset_tag": row["asset_tag"], "priority": "medium", "condition": ""}

    if request.method == "POST":
        errors = []
        device = find_equipment(request.form.get("asset_tag", "").strip())
        if device is None:
            errors.append("No device with that asset tag was found in your facilities.")
        elif device["status"] == "decommissioned":
            errors.append("That device is decommissioned, so faults cannot be reported on it.")
        description = request.form.get("description", "").strip()
        if not description:
            errors.append("Please describe the fault.")
        elif len(description) > 500:
            errors.append("The description must be 500 characters or fewer.")
        priority = request.form.get("priority", "medium")
        if priority not in PRIORITIES:
            errors.append("Choose a valid priority.")
        condition = request.form.get("condition", "")
        if condition and condition not in CONDITIONS:
            errors.append("Choose a valid device condition.")

        if not errors:
            cur = db.execute(
                "INSERT INTO work_orders (equipment_id, wo_type, priority, status, description, reported_by) "
                "VALUES (?, 'corrective', ?, 'open', ?, ?)",
                (device["id"], priority, description, g.user["id"]),
            )
            wo_id = cur.lastrowid
            log(db, g.user["id"], "create", "work_orders", wo_id, f"Fault reported on {device['asset_tag']}")
            # A report can make a device's status worse, never better.
            if condition and SEVERITY[CONDITIONS[condition]] > SEVERITY.get(device["status"], 0):
                set_equipment_status(db, device["id"], CONDITIONS[condition], f"fault report #{wo_id}")
            db.commit()
            flash(f"Fault reported as work order #{wo_id}.", "success")
            return redirect(url_for("workorders.detail", wo_id=wo_id))
        for message in errors:
            flash(message, "danger")
    return render_template("workorders/new.html", form=form, priorities=PRIORITIES)


# --- actions ----------------------------------------------------------------
def back(wo_id):
    return redirect(url_for("workorders.detail", wo_id=wo_id))


@bp.post("/<int:wo_id>/assign")
@roles_required(*MANAGE_ROLES)
def assign(wo_id):
    db = get_db()
    wo = get_wo_or_404(wo_id)
    if wo["status"] not in ("open", "in_progress"):
        flash("This work order is closed.", "warning")
        return back(wo_id)
    tech = db.execute(
        "SELECT id, full_name FROM users WHERE id = ? AND role = 'technician' AND is_active = 1 "
        "AND facility_id = ?", (request.form.get("technician_id", type=int), wo["facility_id"])).fetchone()
    if tech is None:
        flash("Choose a technician from this facility.", "danger")
        return back(wo_id)
    db.execute("UPDATE work_orders SET assigned_to = ? WHERE id = ?", (tech["id"], wo_id))
    log(db, g.user["id"], "update", "work_orders", wo_id, f"assigned to {tech['full_name']}")
    db.commit()
    flash(f"Assigned to {tech['full_name']}.", "success")
    return back(wo_id)


@bp.post("/<int:wo_id>/start")
@login_required
def start(wo_id):
    db = get_db()
    wo = get_wo_or_404(wo_id)
    if not can_work(wo):
        abort(403)
    cur = db.execute(
        "UPDATE work_orders SET status = 'in_progress', started_at = ?, "
        "assigned_to = COALESCE(assigned_to, ?) WHERE id = ? AND status = 'open'",
        (stamp(now_utc()), g.user["id"], wo_id),
    )
    if cur.rowcount:
        log(db, g.user["id"], "update", "work_orders", wo_id, "started work")
        db.commit()
        flash("Work started.", "success")
    else:
        flash("This work order was already started or closed.", "warning")
    return back(wo_id)


@bp.post("/<int:wo_id>/complete")
@login_required
def complete(wo_id):
    db = get_db()
    wo = get_wo_or_404(wo_id)
    if not can_work(wo):
        abort(403)
    errors = []
    notes = request.form.get("resolution_notes", "").strip()
    if not notes:
        errors.append("Describe what was done (resolution notes are required).")
    elif len(notes) > 1000:
        errors.append("Resolution notes must be 1000 characters or fewer.")
    downtime = parse_number(request.form.get("downtime_hours"), "Downtime (hours)", errors)
    cost = parse_number(request.form.get("cost"), "Cost (KSh)", errors, required=False)
    device_status = request.form.get("device_status", "unchanged")
    if device_status != "unchanged" and device_status not in SEVERITY:
        errors.append("Choose the device's condition after the job.")
    if errors:
        for message in errors:
            flash(message, "danger")
        return show_detail(wo, form=request.form)

    now = now_utc()
    closed_at = max(stamp(now), wo["opened_at"])          # never close a job before it opened
    cur = db.execute(
        "UPDATE work_orders SET status = 'completed', started_at = COALESCE(started_at, ?), "
        "closed_at = ?, downtime_hours = ?, cost = ?, resolution_notes = ?, "
        "assigned_to = COALESCE(assigned_to, ?) WHERE id = ? AND status IN ('open', 'in_progress')",
        (stamp(now), closed_at, downtime, cost, notes, g.user["id"], wo_id),
    )
    if not cur.rowcount:
        flash("This work order was already closed.", "warning")
        return back(wo_id)

    if wo["wo_type"] == "ppm":     # completing a PPM moves the schedule forward
        today = now.date()
        db.execute(
            "INSERT INTO maintenance_schedules (equipment_id, interval_days, last_done_date, next_due_date) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(equipment_id) DO UPDATE SET "
            "last_done_date = excluded.last_done_date, next_due_date = excluded.next_due_date",
            (wo["equipment_id"], wo["ppm_interval_days"], today.isoformat(),
             (today + timedelta(days=wo["ppm_interval_days"])).isoformat()),
        )
    if device_status != "unchanged":
        set_equipment_status(db, wo["equipment_id"], device_status, f"work order #{wo_id} completed")
    log(db, g.user["id"], "update", "work_orders", wo_id,
        f"completed; downtime {downtime:g} h, cost {cost:,.0f}")
    db.commit()
    flash("Work order completed.", "success")
    return back(wo_id)


@bp.post("/<int:wo_id>/cancel")
@roles_required(*MANAGE_ROLES)
def cancel(wo_id):
    db = get_db()
    get_wo_or_404(wo_id)
    cur = db.execute("UPDATE work_orders SET status = 'cancelled', closed_at = ? "
                     "WHERE id = ? AND status IN ('open', 'in_progress')", (stamp(now_utc()), wo_id))
    if cur.rowcount:
        log(db, g.user["id"], "update", "work_orders", wo_id, "cancelled")
        db.commit()
        flash("Work order cancelled.", "info")
    else:
        flash("This work order was already closed.", "warning")
    return back(wo_id)


@bp.post("/generate-ppm")
@roles_required(*MANAGE_ROLES)
def generate_ppm():
    """Open a PPM job for every device whose maintenance is due (or overdue)
    within the next week and that has no open PPM job already."""
    db = get_db()
    clause, params = facility_clause(g.user, "e.facility_id")
    cutoff = (now_utc().date() + timedelta(days=PPM_LOOKAHEAD_DAYS)).isoformat()
    due = db.execute(
        "SELECT e.id, ms.next_due_date, t.risk_score FROM equipment e "
        "JOIN maintenance_schedules ms ON ms.equipment_id = e.id "
        "JOIN equipment_types t ON t.id = e.type_id "
        "WHERE e.status != 'decommissioned' AND ms.next_due_date <= ? "
        "AND NOT EXISTS (SELECT 1 FROM work_orders w WHERE w.equipment_id = e.id "
        "                AND w.wo_type = 'ppm' AND w.status IN ('open', 'in_progress')) "
        f"AND {clause}",
        [cutoff] + params,
    ).fetchall()
    db.executemany(
        "INSERT INTO work_orders (equipment_id, wo_type, priority, status, description, reported_by) "
        "VALUES (?, 'ppm', ?, 'open', ?, ?)",
        [(r["id"], "medium" if r["risk_score"] >= 4 else "low",
          f"Scheduled preventive maintenance (due {r['next_due_date']})", g.user["id"]) for r in due],
    )
    log(db, g.user["id"], "create", "work_orders", None, f"Generated {len(due)} PPM jobs")
    db.commit()
    flash(f"{len(due)} preventive maintenance job(s) created." if due
          else "No new preventive maintenance jobs are needed right now.", "success" if due else "info")
    return redirect(url_for("workorders.index", type="ppm", status="open"))
