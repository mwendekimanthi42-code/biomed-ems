"""Template filters for displaying values consistently."""


def ksh(value):
    """1800000 -> 'KSh 1,800,000' (all money in this system is Kenyan shillings)."""
    if value is None or value == "":
        return "-"
    return f"KSh {float(value):,.0f}"


def label(value):
    """'partially_functional' -> 'Partially functional'."""
    return str(value).replace("_", " ").capitalize() if value else "-"
