-- =====================================================================
-- Script 06: SECURITY - Role-Based Access Control (RBAC) + masking
--            + views for department-level (row-level) security
-- (SQLite 3)
-- ---------------------------------------------------------------------
-- SQLite is a FILE database: it has no user accounts and no GRANT
-- command. So security is built in three layers:
--
--  1. IN THE DATABASE (this script)
--     - sec_roles / sec_role_permissions : the RBAC rules, stored as data
--     - sec_users                        : users, role, department, hashed password
--     - masking view v_dim_student_masked: StudentID shown as STU-****-001
--     - department views v_dept_*         : every row carries its department_code
--
--  2. IN THE ACCESS LAYER  (07_Security_Documentation/security_tools/secure_access.py)
--     every user connects through this program. It checks the password,
--     reads the user's role from sec_users and installs an SQLite
--     "authorizer" that BLOCKS anything the role may not do:
--       analyst    -> read-only, cannot read dim_student.student_id
--       dept head  -> can read ONLY its own department's rows (private
--                     temporary copies made at login from the v_dept_* views)
--     Every query (allowed or denied) is written to audit_log.
--
--  3. ON THE FILE  : only the admin and ETL accounts get Windows
--     permission on library_dw.db (see security_implementation.pdf).
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. ROLES
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec_roles (
    role_name    TEXT PRIMARY KEY,
    description  TEXT NOT NULL
);

INSERT OR REPLACE INTO sec_roles (role_name, description) VALUES
 ('dw_admin',     'Full access: all tables, staging, security and audit tables, can change data'),
 ('dw_etl',       'ETL program: may read sources and write staging + warehouse tables'),
 ('dw_analyst',   'Read-only on the whole warehouse; real StudentID hidden (masked)'),
 ('dw_dept_head', 'Read-only, ONLY the rows of his/her own department, masked StudentID'),
 ('dw_backup',    'May read the whole database file to make backups, no changes');

-- ---------------------------------------------------------------------
-- 2. PERMISSION MATRIX  (what each role may do with each object)
--    READ        = SELECT allowed
--    READ_MASKED = SELECT allowed except the real student_id column
--    READ_OWN    = SELECT allowed only through own-department views
--    WRITE       = INSERT / UPDATE / DELETE allowed
--    NONE        = no access
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec_role_permissions (
    role_name    TEXT NOT NULL REFERENCES sec_roles (role_name),
    object_name  TEXT NOT NULL,          -- table, view, or group like 'stg_*'
    permission   TEXT NOT NULL CHECK (permission IN ('READ', 'READ_MASKED', 'READ_OWN', 'WRITE', 'NONE')),
    PRIMARY KEY (role_name, object_name)
);

INSERT OR REPLACE INTO sec_role_permissions (role_name, object_name, permission) VALUES
 ('dw_admin',     '*',              'WRITE'),
 ('dw_etl',       'stg_*',          'WRITE'),
 ('dw_etl',       'etl_*',          'WRITE'),
 ('dw_etl',       'dim_*',          'WRITE'),
 ('dw_etl',       'fact_*',         'WRITE'),
 ('dw_etl',       'sec_*',          'NONE'),
 ('dw_analyst',   'dim_*',          'READ'),
 ('dw_analyst',   'dim_student',    'READ_MASKED'),
 ('dw_analyst',   'fact_*',         'READ'),
 ('dw_analyst',   'v_*',            'READ'),
 ('dw_analyst',   'stg_*',          'NONE'),
 ('dw_analyst',   'sec_*',          'NONE'),
 ('dw_analyst',   'audit_log',      'NONE'),
 ('dw_dept_head', 'my_* (private)', 'READ_OWN'),
 ('dw_dept_head', 'dim_*',          'NONE'),
 ('dw_dept_head', 'fact_*',         'NONE'),
 ('dw_dept_head', 'stg_*',          'NONE'),
 ('dw_backup',    '*',              'READ');

-- ---------------------------------------------------------------------
-- 3. USERS
--    Passwords are NEVER stored in clear text: only a PBKDF2-SHA256 hash
--    with a random salt. The rows are created by:
--        python secure_access.py --setup
--    failed_logins / locked_until: lock the account after 3 wrong passwords.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sec_users (
    username         TEXT PRIMARY KEY,
    role_name        TEXT NOT NULL REFERENCES sec_roles (role_name),
    department_code  TEXT REFERENCES dim_department (department_code),  -- only for dept heads
    password_hash    TEXT NOT NULL,
    salt             TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 1,
    failed_logins    INTEGER NOT NULL DEFAULT 0,
    locked_until     TEXT,
    password_changed TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (role_name <> 'dw_dept_head' OR department_code IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- 4. DATA MASKING VIEW - everything about a student EXCEPT the real ID
--    'STU-2024-001' -> 'STU-****-001' (intake year hidden)
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_dim_student_masked;
CREATE VIEW v_dim_student_masked AS
SELECT student_key, student_id_masked, student_level, year_of_study, gender,
       home_department_code, valid_from, valid_to, is_current
FROM dim_student;

-- ---------------------------------------------------------------------
-- 5. DEPARTMENT VIEWS - one row per fact, with the department_code.
--    At login secure_access.py copies the rows of the head's department
--    into private temporary tables, for example
--    head_cs  ->  my_book_loans = v_dept_book_loans WHERE department_code = 'CS'
--    The head can read only those private tables. Student IDs are MASKED.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_dept_book_loans;
CREATE VIEW v_dept_book_loans AS
SELECT dp.department_code,
       d.full_date          AS checkout_date,
       d.month_label,
       s.student_id_masked  AS student,
       s.student_level,
       b.title,
       b.book_category,
       f.loan_duration_days,
       f.is_returned,
       f.is_overdue
FROM fact_book_loan f
JOIN dim_date d        ON d.date_key = f.checkout_date_key
JOIN dim_student s     ON s.student_key = f.student_key
JOIN dim_book b        ON b.book_key = f.book_key
JOIN dim_department dp ON dp.department_key = f.department_key;

DROP VIEW IF EXISTS v_dept_digital_usage;
CREATE VIEW v_dept_digital_usage AS
SELECT dp.department_code,
       d.full_date AS download_date, d.month_label,
       ut.user_type, r.resource_title, r.resource_type,
       f.download_count, f.duration_minutes
FROM fact_digital_usage f
JOIN dim_date d        ON d.date_key = f.date_key
JOIN dim_user_type ut  ON ut.user_type_key = f.user_type_key
JOIN dim_resource r    ON r.resource_key = f.resource_key
JOIN dim_department dp ON dp.department_key = f.department_key;

DROP VIEW IF EXISTS v_dept_room_bookings;
CREATE VIEW v_dept_room_bookings AS
SELECT dp.department_code,
       d.full_date AS booking_date, d.day_name, d.month_label,
       t.slot_label, rm.room_number, s.student_id_masked AS student,
       p.purpose_name, f.duration_hours
FROM fact_room_booking f
JOIN dim_date d             ON d.date_key = f.date_key
JOIN dim_time_slot t        ON t.time_slot_key = f.time_slot_key
JOIN dim_room rm            ON rm.room_key = f.room_key
JOIN dim_student s          ON s.student_key = f.student_key
JOIN dim_booking_purpose p  ON p.purpose_key = f.purpose_key
JOIN dim_department dp      ON dp.department_key = f.department_key;

DROP VIEW IF EXISTS v_dept_monthly_summary;
-- (written out in full, NOT through v_usage_cube: a department head must
--  only read data through his/her own filtered view)
CREATE VIEW v_dept_monthly_summary AS
SELECT dp.department_code,
       d.month_label,
       SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
       SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
       SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings
FROM (SELECT checkout_date_key AS date_key, department_key, 'Book Loans' AS service, loan_count AS usage_count
      FROM fact_book_loan
      UNION ALL
      SELECT date_key, department_key, 'Digital Downloads', download_count FROM fact_digital_usage
      UNION ALL
      SELECT date_key, department_key, 'Room Bookings', booking_count FROM fact_room_booking) u
JOIN dim_date d        ON d.date_key = u.date_key
JOIN dim_department dp ON dp.department_key = u.department_key
GROUP BY dp.department_code, d.month_label;

-- ---------------------------------------------------------------------
-- 6. CHECK: the permission matrix as a readable table
-- ---------------------------------------------------------------------
SELECT r.role_name, r.description, p.object_name, p.permission
FROM sec_roles r
LEFT JOIN sec_role_permissions p ON p.role_name = r.role_name
ORDER BY r.role_name, p.object_name;
