"""One place that writes to the audit log (who did what, to which record)."""


def log(db, user_id, action, table_name, record_id, details):
    db.execute(
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, action, table_name, record_id, details),
    )
