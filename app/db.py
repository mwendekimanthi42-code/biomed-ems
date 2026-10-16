"""Database connection helpers: one SQLite connection per request."""
import sqlite3

from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row            # rows behave like dictionaries
        g.db.execute("PRAGMA foreign_keys = ON")   # SQLite forgets this on every new connection
    return g.db


def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
