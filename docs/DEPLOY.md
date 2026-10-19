# Deploying the demo

The app is designed to run on a free host as a **public demo with fictional data**. Do not put real hospital records on it.

Two things apply to every host:
- Set a long random `SECRET_KEY`. In production the app refuses to start with the built-in default.
- **Never set `APP_ENV=production` on your own computer.** It makes session cookies HTTPS-only, so login fails over plain `http://localhost`.

Generate a key with: `python -c "import secrets; print(secrets.token_hex(32))"`

## Option A: Render (least maintenance)

Render's free web services sleep after 15 minutes without visitors, and their disk is temporary, so the SQLite file disappears whenever the service restarts. This project handles that: with `AUTO_SEED=1`, `wsgi.py` rebuilds the fictional demo database on start-up (under a second). The trade-off is that demo edits are lost on each restart, which is actually good for a demo. Free services also take roughly 30 to 60 seconds to wake up after sleeping.

1. Push the project to GitHub (including `render.yaml`, `requirements.txt`, and `wsgi.py`).
2. In Render, choose **New, then Blueprint**, and select your repository. Render reads `render.yaml` and proposes the service. Apply it.
3. Wait for the build. Your demo will be at `https://<service-name>.onrender.com`.
4. If the build complains about the Python version, change `PYTHON_VERSION` in the service's environment settings to one Render supports (see Render's Python documentation), then redeploy.
5. Check `/healthz` returns `ok`, then log in as each role.

Manual alternative (same result): create a **Web Service** from the repository with build command `pip install -r requirements.txt` and start command `gunicorn wsgi:app --workers 1 --bind 0.0.0.0:$PORT`, and set these environment variables: `APP_ENV=production`, `AUTO_SEED=1`, `DEMO_MODE=1`, and `SECRET_KEY` (your random key). Keep **one worker**, so two workers do not both try to build the database.

Free-tier terms change, so check Render's current free-tier page before relying on it.

## Option B: PythonAnywhere (keeps its files)

The free account keeps your SQLite file between visits, but it allows one web app, a daily CPU allowance (about 100 CPU-seconds at the time of writing), and **free web apps expire after one month unless you extend them** from the Web tab. Put a reminder in your calendar, or the link will die.

1. Create a free account and open a **Bash** console.
2. Get the code and install it:
   ```bash
   git clone https://github.com/<your-username>/biomed-ems.git
   cd biomed-ems
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python seed_db.py
   ```
3. On the **Web** tab, add a new web app with **manual configuration**, and pick the same Python version you used above. Set the virtualenv path to `/home/<username>/biomed-ems/venv`.
4. Open the WSGI configuration file from that tab, replace its contents with the code below, and save:
   ```python
   import os, sys
   path = "/home/<username>/biomed-ems"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["APP_ENV"] = "production"
   os.environ["SECRET_KEY"] = "<paste your long random key>"
   os.environ["DEMO_MODE"] = "1"
   from wsgi import app as application
   ```
5. Click **Reload**, then visit `https://<username>.pythonanywhere.com`.

## After deploying

- [ ] Open the live link in a private window and log in as each of the five roles.
- [ ] Put the link at the top of your README, in your portfolio, and on LinkedIn.
- [ ] Note on the page or README that the first load may be slow on free hosting.
- [ ] If you ever want to show real data, switch to a paid host with PostgreSQL and turn `DEMO_MODE` off first.
