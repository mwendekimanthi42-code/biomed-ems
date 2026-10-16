"""The multi-facility rule: who is allowed to see which facilities' data."""


def facility_clause(user, column):
    """Return (sql_condition, params) limiting a query to what `user` may see.

    `column` is the facility id column in the query, e.g. "e.facility_id".
    The condition text is built only from fixed strings; user values always
    travel separately as parameters, which keeps queries safe from SQL injection.
    """
    role = user["role"]
    if role == "system_admin":
        return "1 = 1", []
    if role == "county_officer":
        return f"{column} IN (SELECT id FROM facilities WHERE county = ?)", [user["county"]]
    return f"{column} = ?", [user["facility_id"]]


def scope_label(user):
    """Short text describing what the user can see, for the screen."""
    if user["role"] == "system_admin":
        return "All facilities"
    if user["role"] == "county_officer":
        return f"{user['county']} County"
    return user["facility_name"]
