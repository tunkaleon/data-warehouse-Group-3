"""
=====================================================================
 app.py  -  WEB DASHBOARDS for the University Library data warehouse
=====================================================================
 A small Flask web site with a LOGIN page and three dashboards:

   user           role (sec_users)   dashboard it may open
   -------------  -----------------  -------------------------------
   director       dw_analyst         Executive   (whole library)
   head_cs/eng/bus dw_dept_head      Department  (ONLY own department)
   ops_manager    dw_analyst         Operational (daily operations)

 SECURITY - nothing new is invented here, the web site re-uses
 07_Security_Documentation/security_tools/secure_access.py:
   * login(): PBKDF2 password check, lock after 3 wrong passwords,
     every login written to audit_log
   * Session: SQLite connection with the role's AUTHORIZER, so the
     database itself refuses forbidden tables (a head can only read
     his own my_* tables, students are always masked)
 Users without a dashboard (lib_admin, etl_service, backup_user ...) are
 refused, and opening another user's dashboard gives "403 Forbidden".

 HOW TO RUN (from this folder)
     pip install flask
     python ..\07_Security_Documentation\security_tools\secure_access.py --setup   (once)
     python app.py
     open  http://127.0.0.1:5000  in the browser
=====================================================================
"""

import sys
import secrets
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session, abort

# --- re-use the security gate of the project -------------------------------
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "07_Security_Documentation" / "security_tools"))
import secure_access as sa          # noqa: E402  (import after the path is set)
import dashboard_data as dd         # noqa: E402

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)          # new key at every start = old cookies stop working
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# Which dashboard each user opens. Department heads are recognised by their ROLE.
DASHBOARD_OF_USER = {"director": "executive", "ops_manager": "operational"}
DASHBOARD_OF_ROLE = {"dw_dept_head": "department"}
TITLES = {"executive": "Executive Dashboard", "department": "Department Dashboard",
          "operational": "Operational Dashboard"}

# Open database sessions of the logged-in users: token -> secure_access.Session
# (kept on the server; the browser only gets a random token in a signed cookie)
OPEN_SESSIONS = {}


def dashboard_for(user_session):
    """Return 'executive' / 'department' / 'operational', or None (no dashboard)."""
    return (DASHBOARD_OF_USER.get(user_session.username)
            or DASHBOARD_OF_ROLE.get(user_session.role))


def current_user():
    """The secure_access.Session of the browser that sent this request (or None)."""
    return OPEN_SESSIONS.get(session.get("token"))


# =====================================================================
# LOGIN / LOGOUT
# =====================================================================
@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = sa.login(username, password)          # checks hash, lock-out, writes audit_log
        except sa.AccessDenied as e:
            error = str(e)
        else:
            if dashboard_for(user) is None:              # e.g. lib_admin, etl_service, backup_user
                sa.audit(user.username, user.role, "WEB_DENIED", details="role has no web dashboard")
                user.close()
                error = "Your role has no web dashboard (use the tools for your role)."
            else:
                token = secrets.token_hex(16)
                OPEN_SESSIONS[token] = user
                session.clear()
                session["token"] = token
                return redirect(url_for("dashboard", name=dashboard_for(user)))
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    user = OPEN_SESSIONS.pop(session.pop("token", None), None)
    if user:
        sa.audit(user.username, user.role, "LOGOUT")
        user.close()                                     # the private my_* tables are deleted
    return redirect(url_for("login"))


# =====================================================================
# DASHBOARDS
# =====================================================================
@app.route("/dashboard/<name>")
def dashboard(name):
    user = current_user()
    if user is None:
        return redirect(url_for("login"))
    if name not in TITLES:
        abort(404)
    if dashboard_for(user) != name:                      # role-based access to the PAGES
        sa.audit(user.username, user.role, "WEB_DENIED", obj=name, details="dashboard of another role")
        abort(403)

    year = request.args.get("year", type=int)
    if name == "executive":
        data = dd.executive_data(user, year or 2025)
    elif name == "department":
        data = dd.department_data(user, year)            # year None = all years
    else:
        data = dd.operational_data(user)
    sa.audit(user.username, user.role, "WEB_VIEW", obj=name, details=f"year={year}" if year else None)
    return render_template(f"{name}.html", data=data, user=user, title=TITLES[name])


@app.errorhandler(403)
def forbidden(_):
    user = current_user()
    home = url_for("dashboard", name=dashboard_for(user)) if user else url_for("login")
    return render_template("forbidden.html", home=home, user=user), 403


if __name__ == "__main__":
    print("Library web dashboards:  http://127.0.0.1:5000   (Ctrl+C to stop)")
    # threaded=False: every SQLite connection stays in the one thread that created it
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=False)
