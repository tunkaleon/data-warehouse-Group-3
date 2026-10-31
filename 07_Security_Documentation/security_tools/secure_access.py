"""
=====================================================================
 secure_access.py  -  the SECURITY GATE of the library data warehouse
=====================================================================
 SQLite has no user accounts, so every person reaches the warehouse
 through this program. It implements:

   1. AUTHENTICATION : username + password (stored only as a salted
                       PBKDF2-SHA256 hash), account locked for 1 day
                       after 3 wrong passwords, password expiry 90 days
   2. RBAC           : the role in sec_users decides what is allowed.
                       Enforced by SQLite's "authorizer": SQLite asks this
                       program before reading ANY column of ANY table and
                       before ANY change - forbidden actions are refused.
                         dw_admin     everything
                         dw_etl       staging + warehouse, no security tables
                         dw_analyst   read-only, real student_id refused (masking)
                         dw_dept_head read-only, only "my_*" tables of own department
   3. MASKING        : analysts and heads only ever see STU-****-001
   4. ROW-LEVEL      : at login a head gets PRIVATE temporary tables
      SECURITY         my_book_loans, my_digital_usage, my_room_bookings and
                       my_monthly_summary that contain ONLY his/her department
                       (they disappear at logout). The authorizer lets a head
                       read these private tables and nothing else.
   5. AUDIT LOG      : every login and every query (allowed or refused)
                       is written to the audit_log table

 HOW TO RUN (from this folder)
     python secure_access.py --setup          create the demo users (once)
     python secure_access.py --demo           run all security tests and show the results
     python secure_access.py --user head_cs   log in and type SQL yourself
=====================================================================
"""

import os
import sys
import hashlib
import secrets
import sqlite3
import getpass
from pathlib import Path
from datetime import datetime, timedelta

HERE = Path(__file__).resolve().parent
DB_FILE = HERE.parent.parent / "03_Database_Files" / "library_dw.db"

MAX_FAILED_LOGINS = 3
LOCK_HOURS = 24
PASSWORD_DAYS = 90
PBKDF2_ROUNDS = 200_000

# Demo users: (username, role, department, password).
# CHANGE THESE PASSWORDS for any real use (python secure_access.py --setup
# stores only the hash; the clear password is not kept in the database).
DEMO_USERS = [
    ("lib_admin",      "dw_admin",     None,  "Adm1n#Library2026!"),
    ("etl_service",    "dw_etl",       None,  "Etl#Service2026!"),
    ("director",       "dw_analyst",   None,  "Dir#Library2026!"),
    ("ops_manager",    "dw_analyst",   None,  "Ops#Library2026!"),   # web Operational dashboard
    ("analyst_amina",  "dw_analyst",   None,  "Analyst#Amina2026!"),
    ("powerbi_reader", "dw_analyst",   None,  "PowerBI#Reader2026!"),
    ("head_cs",        "dw_dept_head", "CS",  "Head#CompSci2026!"),
    ("head_eng",       "dw_dept_head", "ENG", "Head#Engineer2026!"),
    ("head_bus",       "dw_dept_head", "BUS", "Head#Business2026!"),
    ("backup_user",    "dw_backup",    None,  "Backup#Library2026!"),
]

# Department views that are copied into private "my_..." tables for a department head
DEPT_VIEWS = {"my_book_loans": "v_dept_book_loans", "my_digital_usage": "v_dept_digital_usage",
              "my_room_bookings": "v_dept_room_bookings", "my_monthly_summary": "v_dept_monthly_summary"}


# =====================================================================
# 1. PASSWORDS
# =====================================================================
def hash_password(password, salt):
    """PBKDF2-SHA256: slow on purpose, so stolen hashes are hard to crack."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()


def admin_connection():
    """Internal connection (full rights) used only by this program for logins and audit rows."""
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def audit(username, role, action, obj=None, details=None, rows=None):
    """Write one row into audit_log (with a separate connection, so a refused query is logged too)."""
    con = admin_connection()
    con.execute("INSERT INTO audit_log (db_user, user_role, action, object_name, details, rows_returned) "
                "VALUES (?, ?, ?, ?, ?, ?)", (username, role, action, obj, details, rows))
    con.commit()
    con.close()


def setup_users():
    """Create (or reset) the demo users with hashed passwords."""
    con = admin_connection()
    for username, role, dept, password in DEMO_USERS:
        salt = secrets.token_hex(16)                      # a new random salt for every user
        con.execute("INSERT OR REPLACE INTO sec_users (username, role_name, department_code, password_hash, "
                    "salt, is_active, failed_logins, locked_until, password_changed) "
                    "VALUES (?, ?, ?, ?, ?, 1, 0, NULL, datetime('now'))",
                    (username, role, dept, hash_password(password, salt), salt))
    con.commit()
    print(f"{len(DEMO_USERS)} users created. Passwords are stored as PBKDF2 hashes only:")
    for row in con.execute("SELECT username, role_name, IFNULL(department_code, '-'), "
                           "substr(password_hash, 1, 16) || '...' FROM sec_users ORDER BY role_name"):
        print("   {:15s} {:13s} {:4s} {}".format(*row))
    con.close()


# =====================================================================
# 2. LOGIN
# =====================================================================
class AccessDenied(Exception):
    pass


def login(username, password):
    """Check the password. Returns a Session, or raises AccessDenied."""
    con = admin_connection()
    row = con.execute("SELECT role_name, department_code, password_hash, salt, is_active, failed_logins, "
                      "locked_until, password_changed FROM sec_users WHERE username = ?", (username,)).fetchone()
    if row is None:
        con.close()
        audit(username, None, "LOGIN_FAILED", details="unknown user")
        raise AccessDenied("Wrong username or password")       # same message: do not reveal which one
    role, dept, pw_hash, salt, active, failed, locked_until, changed = row

    if not active:
        con.close()
        audit(username, role, "LOGIN_FAILED", details="account disabled")
        raise AccessDenied("Account disabled")
    if locked_until and datetime.fromisoformat(locked_until) > datetime.now():
        con.close()
        audit(username, role, "LOGIN_FAILED", details="account locked")
        raise AccessDenied(f"Account locked until {locked_until}")

    if not secrets.compare_digest(hash_password(password, salt), pw_hash):
        failed += 1
        lock = (datetime.now() + timedelta(hours=LOCK_HOURS)).isoformat(timespec="seconds") \
            if failed >= MAX_FAILED_LOGINS else None
        con.execute("UPDATE sec_users SET failed_logins = ?, locked_until = ? WHERE username = ?",
                    (failed, lock, username))
        con.commit()
        con.close()
        audit(username, role, "LOGIN_FAILED", details=f"wrong password ({failed}/{MAX_FAILED_LOGINS})"
                                                      + (" -> ACCOUNT LOCKED" if lock else ""))
        raise AccessDenied("Wrong username or password" + (" - account is now LOCKED" if lock else ""))

    con.execute("UPDATE sec_users SET failed_logins = 0, locked_until = NULL WHERE username = ?", (username,))
    con.commit()
    con.close()
    expired = datetime.fromisoformat(changed) < datetime.now() - timedelta(days=PASSWORD_DAYS)
    audit(username, role, "LOGIN_OK", details=f"department={dept}" if dept else None)
    return Session(username, role, dept, password_expired=expired)


# =====================================================================
# 3. SESSION with the role's AUTHORIZER
# =====================================================================
WRITE_ACTIONS = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}
READ_ONLY_OK = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
SCHEMA_TABLES = {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema"}


class Session:
    def __init__(self, username, role, department, password_expired=False):
        self.username, self.role, self.department = username, role, department
        self.password_expired = password_expired
        read_only = role in ("dw_analyst", "dw_dept_head", "dw_backup")
        if read_only:
            # open the FILE read-only: even a bug in the rules below cannot change data
            self.con = sqlite3.connect(DB_FILE.as_uri() + "?mode=ro", uri=True)
        else:
            self.con = sqlite3.connect(DB_FILE)
            self.con.execute("PRAGMA foreign_keys = ON")
        if role == "dw_dept_head":
            self._create_my_views()
        self.con.set_authorizer(self._authorizer)        # from now on SQLite asks before every access

    def _create_my_views(self):
        """Row-level security: copy ONLY this head's department rows into private TEMP
        tables (they live in memory for this session and disappear at logout).
        This runs BEFORE the authorizer is switched on."""
        for my_table, dept_view in DEPT_VIEWS.items():
            self.con.execute(f"CREATE TEMP TABLE {my_table} AS "
                             f"SELECT * FROM {dept_view} WHERE department_code = ?", (self.department,))

    def _authorizer(self, action, arg1, arg2, db_name, source_view):
        """Called by SQLite for every step of a query. Return SQLITE_OK or SQLITE_DENY.
        For a column read: arg1 = table, arg2 = column, source_view = view that is reading it."""
        ok, deny = sqlite3.SQLITE_OK, sqlite3.SQLITE_DENY
        if self.role == "dw_admin":
            return ok
        table = (arg1 or "").lower()

        if self.role in ("dw_etl", "dw_backup"):
            if table.startswith("sec_") or (self.role == "dw_etl" and table == "audit_log"):
                return deny
            if self.role == "dw_backup" and action in WRITE_ACTIONS:
                return deny
            return ok

        # ---- read-only roles from here ----
        if action not in READ_ONLY_OK:
            return deny                                  # no INSERT/UPDATE/DELETE/CREATE/PRAGMA/ATTACH...
        if action != sqlite3.SQLITE_READ or table in SCHEMA_TABLES:
            return ok

        if self.role == "dw_analyst":
            allowed = table.startswith(("dim_", "fact_"))
            if table == "dim_student" and (arg2 or "").lower() == "student_id":
                return deny                              # MASKING: the real ID is never readable
            return ok if allowed else deny

        if self.role == "dw_dept_head":
            # allowed: ONLY the private my_* tables in the "temp" schema (own department)
            return ok if (db_name == "temp" and table in DEPT_VIEWS) else deny
        return deny

    def query(self, sql):
        """Run one SQL statement; every attempt is written to the audit log."""
        try:
            cur = self.con.execute(sql)
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description] if cur.description else []
            self.con.commit()
            audit(self.username, self.role, "QUERY", details=sql.strip()[:500], rows=len(rows))
            return columns, rows
        except sqlite3.DatabaseError as e:
            audit(self.username, self.role, "DENIED", details=f"{sql.strip()[:400]}  ->  {e}")
            raise AccessDenied(str(e)) from None

    def close(self):
        self.con.close()


# =====================================================================
# 4. DEMO - the security tests (used for the presentation and the report)
# =====================================================================
def show(title, func):
    """Run one test and print OK / REFUSED with the result."""
    try:
        cols, rows = func()
        preview = rows[:3]
        print(f"  OK       {title}\n           -> {cols} {preview}{' ...' if len(rows) > 3 else ''}")
    except AccessDenied as e:
        print(f"  REFUSED  {title}\n           -> {e}")


def demo():
    print("=" * 78)
    print(" SECURITY TESTS - library_dw.db")
    print("=" * 78)
    passwords = {u: p for u, _, _, p in DEMO_USERS}

    print("\n[1] ANALYST (analyst_amina): read-only, masked StudentID")
    s = login("analyst_amina", passwords["analyst_amina"])
    show("SELECT COUNT(*) FROM fact_book_loan", lambda: s.query("SELECT COUNT(*) FROM fact_book_loan"))
    show("SELECT student_id_masked, student_level FROM dim_student LIMIT 3",
         lambda: s.query("SELECT student_id_masked, student_level FROM dim_student WHERE student_key > 1 LIMIT 3"))
    show("SELECT student_id FROM dim_student          (real ID)",
         lambda: s.query("SELECT student_id FROM dim_student LIMIT 3"))
    show("SELECT * FROM dim_student                    (includes real ID)",
         lambda: s.query("SELECT * FROM dim_student LIMIT 3"))
    show("DELETE FROM fact_book_loan WHERE loan_key = 1",
         lambda: s.query("DELETE FROM fact_book_loan WHERE loan_key = 1"))
    show("SELECT * FROM stg_book_transactions         (staging area)",
         lambda: s.query("SELECT * FROM stg_book_transactions LIMIT 1"))
    show("SELECT * FROM sec_users                      (password hashes)",
         lambda: s.query("SELECT * FROM sec_users"))
    s.close()

    for head in ("head_cs", "head_eng"):
        print(f"\n[2] DEPARTMENT HEAD ({head}): only own department")
        s = login(head, passwords[head])
        show("SELECT department_code, COUNT(*) FROM my_book_loans GROUP BY 1",
             lambda: s.query("SELECT department_code, COUNT(*) FROM my_book_loans GROUP BY department_code"))
        show("SELECT month_label, book_loans, digital_downloads FROM my_monthly_summary",
             lambda: s.query("SELECT month_label, book_loans, digital_downloads, room_bookings "
                             "FROM my_monthly_summary ORDER BY month_label DESC"))
        show("SELECT student, title FROM my_book_loans LIMIT 2",
             lambda: s.query("SELECT student, title FROM my_book_loans LIMIT 2"))
        show("SELECT COUNT(*) FROM fact_book_loan          (all departments)",
             lambda: s.query("SELECT COUNT(*) FROM fact_book_loan"))
        show("SELECT COUNT(*) FROM v_dept_book_loans       (all departments)",
             lambda: s.query("SELECT COUNT(*) FROM v_dept_book_loans"))
        s.close()

    print("\n[3] WRONG PASSWORD 3 TIMES (head_bus) -> account locked")
    for attempt in range(1, 4):
        try:
            login("head_bus", "guess" + str(attempt))
        except AccessDenied as e:
            print(f"  attempt {attempt}: {e}")
    try:
        login("head_bus", passwords["head_bus"])
        print("  correct password: logged in")
    except AccessDenied as e:
        print(f"  correct password now: {e}")
    con = admin_connection()                     # unlock again so the demo can be repeated
    con.execute("UPDATE sec_users SET failed_logins = 0, locked_until = NULL WHERE username = 'head_bus'")
    con.commit()
    con.close()
    print("  (admin unlocked head_bus again for the next demo)")

    print("\n[4] ADMIN (lib_admin): a change is recorded by the audit trigger")
    s = login("lib_admin", passwords["lib_admin"])
    show("UPDATE dim_student SET valid_to = '9999-12-30' WHERE student_key = 2",
         lambda: s.query("UPDATE dim_student SET valid_to = '9999-12-30' WHERE student_key = 2"))
    show("UPDATE dim_student SET valid_to = '9999-12-31' WHERE student_key = 2  (undo)",
         lambda: s.query("UPDATE dim_student SET valid_to = '9999-12-31' WHERE student_key = 2"))
    s.close()

    print("\n[5] AUDIT LOG - the last 12 events")
    con = admin_connection()
    for r in con.execute("SELECT event_time, db_user, action, IFNULL(object_name, ''), "
                         "substr(IFNULL(details, ''), 1, 70) FROM audit_log ORDER BY audit_id DESC LIMIT 12"):
        print("  {} {:14s} {:13s} {:12s} {}".format(*r))
    con.close()


# =====================================================================
# 5. INTERACTIVE MODE
# =====================================================================
def interactive(username):
    try:
        s = login(username, getpass.getpass(f"Password for {username}: "))
    except AccessDenied as e:
        sys.exit(f"Login refused: {e}")
    print(f"Logged in as {username} ({s.role}{', ' + s.department if s.department else ''}).")
    if s.password_expired:
        print("Your password is older than 90 days - ask the admin to reset it.")
    if s.role == "dw_dept_head":
        print("Your tables: " + ", ".join(DEPT_VIEWS))
    print("Type one SQL statement per line, or 'exit'.")
    while True:
        sql = input("SQL> ").strip()
        if sql.lower() in ("exit", "quit"):
            break
        if not sql:
            continue
        try:
            cols, rows = s.query(sql)
            print(" | ".join(cols))
            for r in rows[:50]:
                print(" | ".join(str(v) for v in r))
            print(f"({len(rows)} rows)")
        except AccessDenied as e:
            print(f"REFUSED: {e}")
    s.close()


if __name__ == "__main__":
    if not DB_FILE.exists():
        sys.exit(f"Database not found: {DB_FILE}\nRun 04_ETL_Files/etl_script.py first.")
    if "--setup" in sys.argv:
        setup_users()
    elif "--demo" in sys.argv:
        demo()
    elif "--user" in sys.argv:
        interactive(sys.argv[sys.argv.index("--user") + 1])
    else:
        print(__doc__)
