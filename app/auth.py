"""Login, logout, form protection (CSRF), and role checks."""
import functools
import secrets
from urllib.parse import urlparse

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

# Checked when the email is unknown, so "no such user" and "wrong password"
# take about the same time and reveal nothing to an attacker.
DUMMY_HASH = generate_password_hash("not-a-real-password")


# --- CSRF protection --------------------------------------------------------
def csrf_token():
    """A random token stored in the session and embedded in every form."""
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


# --- Who is logged in? ------------------------------------------------------
@bp.before_app_request
def load_logged_in_user():
    g.user = None
    if request.endpoint == "static":
        return
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT u.id, u.full_name, u.email, u.role, u.facility_id, u.county, "
            "       f.name AS facility_name "
            "FROM users u LEFT JOIN facilities f ON f.id = u.facility_id "
            "WHERE u.id = ? AND u.is_active = 1",
            (user_id,),
        ).fetchone()
        if g.user is None:          # account deleted or deactivated: end the session
            session.clear()


@bp.before_app_request
def protect_forms():
    """Reject any POST that does not carry the session's secret token."""
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("_csrf", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Your form expired or was invalid. Please go back and try again.")


# --- Decorators for protecting pages ----------------------------------------
def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped


def roles_required(*roles):
    """Allow only the listed roles, e.g. @roles_required('system_admin')."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            if g.user is None:
                return redirect(url_for("auth.login", next=request.path))
            if g.user["role"] not in roles:
                abort(403)
            return view(**kwargs)
        return wrapped
    return decorator


# --- Helpers ----------------------------------------------------------------
def safe_next(target):
    """Only follow redirects to pages on this site (blocks open-redirect tricks)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        parts = urlparse(target)
        if not parts.scheme and not parts.netloc:
            return target
    return url_for("main.dashboard")


def audit(db, user_id, action, record_id, details):
    db.execute(
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (?, ?, 'users', ?, ?)",
        (user_id, action, record_id, details),
    )


# --- Routes -----------------------------------------------------------------
@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)
        ).fetchone()

        password_ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password)
        if user is not None and password_ok:
            session.clear()                    # fresh session on login
            session["user_id"] = user["id"]
            audit(db, user["id"], "login", user["id"], "Successful login")
            db.commit()
            return redirect(safe_next(request.args.get("next")))

        audit(db, None, "login_failed", None, f"Failed login for {email[:100]}")
        db.commit()
        flash("Invalid email or password.", "danger")   # same message either way

    return render_template("login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
