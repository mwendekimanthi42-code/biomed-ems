"""Main pages: the dashboard."""
from datetime import date

from flask import Blueprint, g, render_template

from . import metrics
from .auth import login_required
from .db import get_db
from .scope import scope_label

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    db, today = get_db(), date.today()
    overview = metrics.overview(db, g.user, today)
    monthly = metrics.monthly_series(db, g.user, today)
    facilities = metrics.facility_comparison(db, g.user, today)
    candidates, _ = metrics.budget_candidates(db, g.user, today)
    chart_data = {
        "status": {"labels": ["Functional", "Partially functional", "Non-functional", "Decommissioned"],
                   "values": [overview["functional"], overview["partial"], overview["non_functional"],
                              overview["decommissioned"]]},
        "monthly": monthly,
        "facilities": {"labels": [f["name"] for f in facilities],
                       "ppm": [f["ppm_pct"] for f in facilities],
                       "functional": [f["functional_pct"] for f in facilities]},
    }
    return render_template("dashboard.html", scope=scope_label(g.user), o=overview, facilities=facilities,
                           attention=candidates[:5], urgent=metrics.urgent_jobs(db, g.user),
                           chart_data=chart_data)
