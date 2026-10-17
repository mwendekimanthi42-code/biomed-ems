"""Application factory for the Biomedical Equipment Management System."""
import os
from pathlib import Path

from flask import Flask, render_template

from . import auth, db, equipment, formatting, main, reports, workorders

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        # Set a real SECRET_KEY environment variable in any real deployment.
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=str(BASE_DIR / "biomed.db"),
        # DEMO_MODE shows the demo accounts on the login page. Turn it off for real use.
        DEMO_MODE=os.environ.get("DEMO_MODE", "1") == "1",
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(equipment.bp)
    app.register_blueprint(workorders.bp)
    app.register_blueprint(reports.bp)

    app.add_template_filter(formatting.ksh, "ksh")
    app.add_template_filter(formatting.label, "label")
    app.add_template_filter(formatting.pct, "pct")
    app.add_template_filter(formatting.num, "num")

    # Make csrf_token() available in every template.
    app.context_processor(lambda: {"csrf_token": auth.csrf_token})

    def show_error(error):
        return render_template("error.html", error=error), error.code

    for code in (400, 403, 404):
        app.register_error_handler(code, show_error)

    return app
