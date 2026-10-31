# 12_Web_Dashboard - web dashboards for three types of users

A small web site (Python **Flask**) on top of the warehouse `03_Database_Files/library_dw.db`.
Each user signs in and sees **only the dashboard of his/her role**.

| Username | Password (demo) | Role in `sec_users` | Dashboard |
|---|---|---|---|
| `director` | `Dir#Library2026!` | dw_analyst | **Executive** - whole library, year filter, vs last year |
| `head_cs` | `Head#CompSci2026!` | dw_dept_head (CS) | **Department** - Computer Science only |
| `head_eng` | `Head#Engineer2026!` | dw_dept_head (ENG) | **Department** - Engineering only |
| `head_bus` | `Head#Business2026!` | dw_dept_head (BUS) | **Department** - Business only |
| `ops_manager` | `Ops#Library2026!` | dw_analyst | **Operational** - rooms and circulation, last 30/60 days |

`lib_admin`, `etl_service`, `analyst_amina`, `powerbi_reader` and `backup_user` are refused: they have no web dashboard.
Change the demo passwords in `secure_access.py` before any real use.

## How to run (Windows)

1. Once: create the users (this also adds `ops_manager`):
   ```
   cd 07_Security_Documentation\security_tools
   python secure_access.py --setup
   ```
2. Double-click **`start_web_dashboard.bat`** (installs Flask the first time, starts the server, opens the browser).
   Or by hand: `pip install flask` then `python app.py` and open **http://127.0.0.1:5000**.
3. Sign in, e.g. `director` / `Dir#Library2026!`. Use **Log out** to switch user.
4. Stop the server: close the black window (or Ctrl+C).

No internet is needed: the charts are drawn by `static/charts.js` (no external library).

## Files

| File | What it does |
|---|---|
| `app.py` | web server: login, logout, which user may open which dashboard (403 otherwise) |
| `dashboard_data.py` | the SQL for each dashboard (runs through the user's secure connection) |
| `templates/*.html` | the pages: login, executive, department, operational, forbidden |
| `static/charts.js` | draws line, bar, column, donut, combo charts and the heat map (SVG) |
| `static/style.css` | look of the pages (same style as the Power BI designs) |
| `start_web_dashboard.bat` | double-click start |

## Security (re-uses `07_Security_Documentation/security_tools/secure_access.py`)

* **Authentication** - `secure_access.login()`: PBKDF2-SHA256 password hashes, account locked for 24 h after 3 wrong passwords.
* **Page access** - each user may open only his/her dashboard; any other URL gives **403 Access denied**.
* **Data access in the database** - every query runs on a connection with the role's SQLite **authorizer**:
  a department head can read ONLY the private `my_*` tables of his own department (row-level security),
  so even a programming mistake cannot show another department. Students appear masked (`STU-****-001`).
* **Audit log** - `LOGIN_OK`, `LOGIN_FAILED`, `WEB_VIEW`, `WEB_DENIED` and `LOGOUT` are written to `audit_log`.
* The server listens only on `127.0.0.1` (this computer). For a real deployment put it behind HTTPS
  (e.g. IIS / nginx) and run it with a production server such as `waitress`.

## Demo script for the presentation (3 minutes)

1. Sign in as `director` -> Executive dashboard; change the year to 2024 (KPIs and "vs last year" change).
2. Type `http://127.0.0.1:5000/dashboard/operational` in the address bar -> **403 Access denied**.
3. Log out, sign in as `head_cs` -> only Computer Science data, masked student IDs.
4. Log out, sign in as `ops_manager` -> peak-time heat map, daily bookings, overdue books, alerts.
5. Log out, sign in with a wrong password 3 times -> the account is locked.
   (Unlock it again with `python secure_access.py --setup`.)
6. Show the `audit_log` table in DB Browser: every step above is recorded.
