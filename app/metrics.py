"""The numbers behind the dashboard and reports.

Every function takes the logged-in user and limits its results to the
facilities that user may see (see scope.py), so no report can leak data.
"""
from datetime import date, timedelta

from .equipment import REPAIR_REVIEW_RATIO
from .scope import facility_clause

RELIABILITY_WINDOW_DAYS = 730            # look-back used for MTBF, MTTR and availability
PRIORITY_WEIGHTS = {"age": 40, "repair": 40, "risk": 20}   # replacement priority score (0-100)


def pct(part, whole):
    return round(100 * part / whole, 1) if whole else None


def month_keys(today, count):
    """['2025-11', ..., '2026-10'] : the last `count` months, oldest first."""
    keys, year, month = [], today.year, today.month
    for _ in range(count):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return keys[::-1]


# --- headline numbers -------------------------------------------------------
def overview(db, user, today):
    clause, params = facility_clause(user, "e.facility_id")
    t = today.isoformat()
    eq = db.execute(
        "SELECT COUNT(*) AS total, "
        "  COALESCE(SUM(e.status != 'decommissioned'), 0) AS active, "
        "  COALESCE(SUM(e.status = 'functional'), 0) AS functional, "
        "  COALESCE(SUM(e.status = 'partially_functional'), 0) AS partial, "
        "  COALESCE(SUM(e.status = 'non_functional'), 0) AS non_functional, "
        "  COALESCE(SUM(e.status = 'decommissioned'), 0) AS decommissioned "
        f"FROM equipment e WHERE {clause}", params).fetchone()
    ppm = db.execute(
        "SELECT COUNT(*) AS scheduled, COALESCE(SUM(ms.next_due_date < ?), 0) AS overdue "
        "FROM equipment e JOIN maintenance_schedules ms ON ms.equipment_id = e.id "
        f"WHERE e.status != 'decommissioned' AND {clause}", [t] + params).fetchone()
    past_life = db.execute(
        "SELECT COUNT(*) FROM equipment e JOIN equipment_types t ON t.id = e.type_id "
        "WHERE e.status != 'decommissioned' AND e.purchase_date IS NOT NULL "
        "AND (julianday(?) - julianday(e.purchase_date)) / 365.25 > t.expected_life_years "
        f"AND {clause}", [t] + params).fetchone()[0]
    jobs = db.execute(
        "SELECT COUNT(*) AS open_jobs, COALESCE(SUM(w.priority IN ('critical', 'high')), 0) AS urgent "
        "FROM work_orders w JOIN equipment e ON e.id = w.equipment_id "
        f"WHERE w.status IN ('open', 'in_progress') AND {clause}", params).fetchone()
    return {
        "total": eq["total"], "active": eq["active"], "functional": eq["functional"],
        "partial": eq["partial"], "non_functional": eq["non_functional"],
        "decommissioned": eq["decommissioned"],
        "functional_pct": pct(eq["functional"], eq["active"]),
        "scheduled": ppm["scheduled"], "ppm_overdue": ppm["overdue"],
        "ppm_pct": pct(ppm["scheduled"] - ppm["overdue"], ppm["scheduled"]),
        "past_life": past_life, "open_jobs": jobs["open_jobs"], "urgent_jobs": jobs["urgent"],
    }


def monthly_series(db, user, today, months=12):
    """Repair downtime and repair cost per month, for the last `months` months."""
    clause, params = facility_clause(user, "e.facility_id")
    keys = month_keys(today, months)
    rows = {r["m"]: r for r in db.execute(
        "SELECT substr(w.closed_at, 1, 7) AS m, SUM(w.downtime_hours) AS downtime, "
        "       SUM(w.cost) AS cost, COUNT(*) AS repairs "
        "FROM work_orders w JOIN equipment e ON e.id = w.equipment_id "
        "WHERE w.wo_type = 'corrective' AND w.status = 'completed' AND w.closed_at >= ? "
        f"AND {clause} GROUP BY m", [keys[0] + "-01"] + params)}
    labels = [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in keys]
    return {
        "labels": labels,
        "downtime": [round(rows[k]["downtime"], 1) if k in rows else 0 for k in keys],
        "cost": [round(rows[k]["cost"]) if k in rows else 0 for k in keys],
        "repairs": [rows[k]["repairs"] if k in rows else 0 for k in keys],
    }


# --- facility comparison (the county officer's view) -------------------------
def facility_comparison(db, user, today):
    t = today.isoformat()
    since = (today - timedelta(days=365)).isoformat()
    f_clause, f_params = facility_clause(user, "f.id")
    e_clause, e_params = facility_clause(user, "e.facility_id")
    facilities = db.execute(
        f"SELECT f.id, f.name, f.county, f.level FROM facilities f WHERE {f_clause} ORDER BY f.name", f_params
    ).fetchall()

    def grouped(sql, args):
        return {r["facility_id"]: dict(r) for r in db.execute(sql, args)}

    devices = grouped(
        "SELECT e.facility_id, COUNT(*) AS active, SUM(e.status = 'functional') AS functional "
        f"FROM equipment e WHERE e.status != 'decommissioned' AND {e_clause} GROUP BY e.facility_id", e_params)
    ppm = grouped(
        "SELECT e.facility_id, COUNT(*) AS scheduled, SUM(ms.next_due_date < ?) AS overdue "
        "FROM equipment e JOIN maintenance_schedules ms ON ms.equipment_id = e.id "
        f"WHERE e.status != 'decommissioned' AND {e_clause} GROUP BY e.facility_id", [t] + e_params)
    jobs = grouped(
        "SELECT e.facility_id, COUNT(*) AS open_jobs FROM work_orders w JOIN equipment e ON e.id = w.equipment_id "
        f"WHERE w.status IN ('open', 'in_progress') AND {e_clause} GROUP BY e.facility_id", e_params)
    repairs = grouped(
        "SELECT e.facility_id, COUNT(*) AS repairs, SUM(w.downtime_hours) AS downtime, SUM(w.cost) AS cost, "
        "       AVG(w.downtime_hours) AS mttr FROM work_orders w JOIN equipment e ON e.id = w.equipment_id "
        "WHERE w.wo_type = 'corrective' AND w.status = 'completed' AND w.closed_at >= ? "
        f"AND {e_clause} GROUP BY e.facility_id", [since] + e_params)

    rows = []
    for f in facilities:
        d, p, j, r = (x.get(f["id"], {}) for x in (devices, ppm, jobs, repairs))
        active, scheduled, overdue = d.get("active", 0), p.get("scheduled", 0), p.get("overdue") or 0
        rows.append({
            "id": f["id"], "name": f["name"], "county": f["county"], "level": f["level"],
            "devices": active, "functional_pct": pct(d.get("functional") or 0, active),
            "ppm_pct": pct(scheduled - overdue, scheduled), "ppm_overdue": overdue,
            "open_jobs": j.get("open_jobs", 0), "repairs": r.get("repairs", 0),
            "downtime": round(r.get("downtime") or 0, 1), "cost": round(r.get("cost") or 0),
            "mttr": round(r["mttr"], 1) if r.get("mttr") is not None else None,
        })
    return rows


# --- reliability: MTBF, MTTR, availability ------------------------------------
def reliability(db, user, today):
    """Per equipment type, over the last RELIABILITY_WINDOW_DAYS days.

    exposure   = hours each active device has existed within the window
    failures   = repair (corrective) work orders opened in the window
    MTTR       = average repair downtime of completed repairs
    MTBF       = (exposure - repair downtime) / failures
    availability = (exposure - repair downtime) / exposure
    """
    clause, params = facility_clause(user, "e.facility_id")
    t = today.isoformat()
    start = (today - timedelta(days=RELIABILITY_WINDOW_DAYS)).isoformat()
    exposure = {r["id"]: dict(r) for r in db.execute(
        "SELECT t.id, t.name, COUNT(*) AS devices, "
        "  SUM(MAX(0, julianday(?) - julianday(MAX(COALESCE(e.purchase_date, ?), ?)))) * 24.0 AS exposure_hours "
        "FROM equipment e JOIN equipment_types t ON t.id = e.type_id "
        f"WHERE e.status != 'decommissioned' AND {clause} GROUP BY t.id", [t, start, start] + params)}
    failures = {r["type_id"]: dict(r) for r in db.execute(
        "SELECT e.type_id, COUNT(*) AS failures, COALESCE(SUM(w.downtime_hours), 0) AS downtime, "
        "       AVG(CASE WHEN w.status = 'completed' THEN w.downtime_hours END) AS mttr "
        "FROM work_orders w JOIN equipment e ON e.id = w.equipment_id "
        "WHERE w.wo_type = 'corrective' AND w.status != 'cancelled' AND w.opened_at >= ? "
        f"AND e.status != 'decommissioned' AND {clause} GROUP BY e.type_id", [start] + params)}

    def build(name, devices, exp_hours, fails, downtime, mttr):
        operating = exp_hours - downtime
        return {"name": name, "devices": devices, "failures": fails,
                "mtbf": round(operating / fails) if fails else None,
                "mttr": round(mttr, 1) if mttr is not None else None,
                "availability": pct(operating, exp_hours),
                "failures_per_device_year": round(fails / (exp_hours / 8766), 2) if exp_hours and fails else 0}

    rows, totals = [], [0, 0.0, 0, 0.0, []]
    for type_id, e in sorted(exposure.items(), key=lambda kv: kv[1]["name"]):
        f = failures.get(type_id, {})
        rows.append(build(e["name"], e["devices"], e["exposure_hours"], f.get("failures", 0),
                          f.get("downtime", 0), f.get("mttr")))
        totals[0] += e["devices"]; totals[1] += e["exposure_hours"]
        totals[2] += f.get("failures", 0); totals[3] += f.get("downtime", 0)
        if f.get("mttr") is not None:
            totals[4].append(f["mttr"])
    overall_mttr = (sum(totals[4]) / len(totals[4])) if totals[4] else None
    return rows, build("All equipment", totals[0], totals[1], totals[2], totals[3], overall_mttr)


# --- replacement planning and budget ------------------------------------------
def budget_candidates(db, user, today):
    """Devices that deserve a replacement decision, ranked by a 0-100 priority score.

    flags:  past_eol      age is beyond the type's expected life
            repair_review lifetime repair spend >= REPAIR_REVIEW_RATIO of replacement cost
            eol_12m       will pass its expected life within the next 12 months
    score = 40 x age (capped at 150% of life) + 40 x repair ratio (capped at 100%) + 20 x risk/5
    """
    clause, params = facility_clause(user, "e.facility_id")
    rows = db.execute(
        "SELECT e.id, e.asset_tag, e.status, e.purchase_date, f.name AS facility, t.name AS type_name, "
        "       t.risk_score, t.expected_life_years, t.est_replacement_cost, "
        "       COALESCE((SELECT SUM(w.cost) FROM work_orders w WHERE w.equipment_id = e.id "
        "                 AND w.wo_type = 'corrective' AND w.status = 'completed'), 0) AS repair_cost "
        "FROM equipment e JOIN facilities f ON f.id = e.facility_id "
        "JOIN equipment_types t ON t.id = e.type_id "
        f"WHERE e.status != 'decommissioned' AND {clause}", params).fetchall()

    candidates = []
    for r in rows:
        age = None
        if r["purchase_date"]:
            age = (today - date.fromisoformat(r["purchase_date"])).days / 365.25
        life, cost = r["expected_life_years"], r["est_replacement_cost"]
        repair_ratio = r["repair_cost"] / cost if cost else 0
        past_eol = age is not None and age > life
        eol_12m = age is not None and age <= life < age + 1
        repair_review = repair_ratio >= REPAIR_REVIEW_RATIO
        if not (past_eol or eol_12m or repair_review):
            continue
        age_ratio = (age / life) if age is not None else 0
        score = (PRIORITY_WEIGHTS["age"] * min(age_ratio / 1.5, 1)
                 + PRIORITY_WEIGHTS["repair"] * min(repair_ratio, 1)
                 + PRIORITY_WEIGHTS["risk"] * r["risk_score"] / 5)
        candidates.append({
            "id": r["id"], "asset_tag": r["asset_tag"], "facility": r["facility"], "type_name": r["type_name"],
            "status": r["status"], "age": round(age, 1) if age is not None else None, "life": life,
            "repair_cost": r["repair_cost"], "repair_ratio": round(repair_ratio * 100), "risk": r["risk_score"],
            "past_eol": past_eol, "eol_12m": eol_12m, "repair_review": repair_review,
            "timing": "review_now" if (past_eol or repair_review) else "plan_12m",
            "score": round(score), "replacement_cost": cost,
        })
    candidates.sort(key=lambda c: (-c["score"], c["asset_tag"]))

    summary = {"review_now": {"count": 0, "cost": 0}, "plan_12m": {"count": 0, "cost": 0}, "by_facility": {}}
    for c in candidates:
        bucket = summary[c["timing"]]
        bucket["count"] += 1
        bucket["cost"] += c["replacement_cost"]
        fac = summary["by_facility"].setdefault(
            c["facility"], {"review_now": 0, "plan_12m": 0, "review_now_cost": 0, "plan_12m_cost": 0})
        fac[c["timing"]] += 1
        fac[c["timing"] + "_cost"] += c["replacement_cost"]
    summary["by_facility"] = dict(sorted(summary["by_facility"].items()))
    return candidates, summary


def urgent_jobs(db, user, limit=5):
    clause, params = facility_clause(user, "e.facility_id")
    return db.execute(
        "SELECT w.id, w.priority, w.status, w.description, w.opened_at, e.asset_tag, f.name AS facility "
        "FROM work_orders w JOIN equipment e ON e.id = w.equipment_id JOIN facilities f ON f.id = e.facility_id "
        "WHERE w.status IN ('open', 'in_progress') AND w.priority IN ('critical', 'high') "
        f"AND {clause} ORDER BY CASE w.priority WHEN 'critical' THEN 0 ELSE 1 END, w.opened_at LIMIT ?",
        params + [limit]).fetchall()
