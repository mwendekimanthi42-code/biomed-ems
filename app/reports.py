"""Printable reports and CSV downloads for engineers and county officers."""
import csv
import io
from datetime import date

from flask import Blueprint, Response, g, render_template

from . import metrics
from .audit import log
from .auth import roles_required
from .db import get_db
from .scope import scope_label

bp = Blueprint("reports", __name__, url_prefix="/reports")
VIEW_ROLES = ("system_admin", "county_officer", "facility_engineer")


def csv_safe(value):
    """Stop spreadsheet programs from running a cell that starts with = + - or @."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def csv_response(filename, header, rows, what):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_safe(v) for v in row])
    db = get_db()
    log(db, g.user["id"], "export", "reports", None, f"Downloaded {what}")
    db.commit()
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}-{date.today().isoformat()}.csv"'})


@bp.route("/")
@roles_required(*VIEW_ROLES)
def index():
    return render_template("reports/index.html", scope=scope_label(g.user))


@bp.route("/audit")
@roles_required(*VIEW_ROLES)
def audit():
    today = date.today()
    rows = metrics.facility_comparison(get_db(), g.user, today)
    return render_template("reports/audit.html", rows=rows, today=today, scope=scope_label(g.user),
                           totals=metrics.overview(get_db(), g.user, today))


@bp.route("/audit.csv")
@roles_required(*VIEW_ROLES)
def audit_csv():
    rows = metrics.facility_comparison(get_db(), g.user, date.today())
    header = ["Facility", "County", "Level", "Active devices", "Functional %", "PPM compliance %",
              "Overdue PPM", "Open work orders", "Repairs (12 months)", "Repair downtime hours (12 months)",
              "Repair cost KSh (12 months)", "Average repair time hours"]
    return csv_response("maintenance-audit", header,
                        [[r["name"], r["county"], r["level"], r["devices"], r["functional_pct"], r["ppm_pct"],
                          r["ppm_overdue"], r["open_jobs"], r["repairs"], r["downtime"], r["cost"], r["mttr"]]
                         for r in rows], "maintenance audit report")


@bp.route("/budget")
@roles_required(*VIEW_ROLES)
def budget():
    today = date.today()
    candidates, summary = metrics.budget_candidates(get_db(), g.user, today)
    return render_template("reports/budget.html", candidates=candidates[:50], total=len(candidates),
                           summary=summary, today=today, scope=scope_label(g.user),
                           weights=metrics.PRIORITY_WEIGHTS, review_ratio=metrics.REPAIR_REVIEW_RATIO)


@bp.route("/budget.csv")
@roles_required(*VIEW_ROLES)
def budget_csv():
    candidates, _ = metrics.budget_candidates(get_db(), g.user, date.today())
    header = ["Rank", "Asset tag", "Facility", "Type", "Status", "Age (years)", "Expected life (years)",
              "Repair spend KSh", "Repair spend % of replacement", "Risk score", "Priority score",
              "Timing", "Estimated replacement cost KSh"]
    timing = {"review_now": "Review now", "plan_12m": "Plan within 12 months"}
    return csv_response("replacement-budget", header,
                        [[i, c["asset_tag"], c["facility"], c["type_name"], c["status"], c["age"], c["life"],
                          round(c["repair_cost"]), c["repair_ratio"], c["risk"], c["score"],
                          timing[c["timing"]], round(c["replacement_cost"])]
                         for i, c in enumerate(candidates, start=1)], "replacement budget report")


@bp.route("/reliability")
@roles_required(*VIEW_ROLES)
def reliability():
    rows, overall = metrics.reliability(get_db(), g.user, date.today())
    return render_template("reports/reliability.html", rows=rows, overall=overall, today=date.today(),
                           scope=scope_label(g.user), window=metrics.RELIABILITY_WINDOW_DAYS)
