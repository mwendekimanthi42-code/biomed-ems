"""Main pages. For now: a dashboard that proves facility scoping works."""
from flask import Blueprint, g, render_template

from .auth import login_required
from .db import get_db
from .scope import facility_clause, scope_label

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    db = get_db()

    clause, params = facility_clause(g.user, "e.facility_id")
    equipment = db.execute(
        f"SELECT COUNT(*) FROM equipment e WHERE {clause}", params
    ).fetchone()[0]
    open_jobs = db.execute(
        "SELECT COUNT(*) FROM work_orders w JOIN equipment e ON e.id = w.equipment_id "
        f"WHERE w.status IN ('open', 'in_progress') AND {clause}", params
    ).fetchone()[0]

    clause, params = facility_clause(g.user, "f.id")
    facilities = db.execute(
        f"SELECT COUNT(*) FROM facilities f WHERE {clause}", params
    ).fetchone()[0]

    return render_template(
        "dashboard.html",
        scope=scope_label(g.user),
        equipment=equipment,
        open_jobs=open_jobs,
        facilities=facilities,
    )
