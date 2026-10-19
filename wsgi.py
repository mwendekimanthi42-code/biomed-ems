"""Entry point for hosting platforms:  gunicorn wsgi:app

Set AUTO_SEED=1 to build the fictional demo database on start-up whenever the
database file is missing. Hosts with a temporary disk (such as Render's free
tier) need this, because the file disappears whenever the service restarts.
"""
import os
from pathlib import Path

from app import create_app

app = application = create_app()

if os.environ.get("AUTO_SEED") == "1" and not Path(app.config["DATABASE"]).exists():
    import seed_db
    seed_db.main(quiet=True)
