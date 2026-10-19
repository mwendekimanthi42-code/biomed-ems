"""Template filters for displaying values consistently."""
from datetime import datetime, timedelta

EAT_OFFSET = timedelta(hours=3)   # Kenya is UTC+3 all year round (no daylight saving)


def ksh(value):
    """1800000 -> 'KSh 1,800,000' (all money in this system is Kenyan shillings)."""
    if value is None or value == "":
        return "-"
    return f"KSh {float(value):,.0f}"


def label(value):
    """'partially_functional' -> 'Partially functional'."""
    return str(value).replace("_", " ").capitalize() if value else "-"


def pct(value):
    """83.456 -> '83.5%'; missing values show as a dash."""
    return "-" if value is None else f"{value:.1f}%"


def num(value):
    """12345.6 -> '12,346'."""
    return "-" if value is None else f"{value:,.0f}"


def _to_eat(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S") + EAT_OFFSET
    except (TypeError, ValueError):
        return None


def eat_time(value):
    """Timestamps are stored in UTC; show them in Nairobi time: '17 Oct 2026, 15:04'."""
    if not value:
        return "-"
    local = _to_eat(value)
    return local.strftime("%d %b %Y, %H:%M") if local else str(value)


def eat_date(value):
    """'2026-10-17 21:30:00' (UTC) -> '18 Oct 2026' (Nairobi date)."""
    if not value:
        return "-"
    local = _to_eat(value)
    return local.strftime("%d %b %Y") if local else str(value)[:10]
