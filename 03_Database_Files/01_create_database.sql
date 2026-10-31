-- =====================================================================
-- University Library Analytics - Data Warehouse        (SQLite 3)
-- Script 01: Create / reset the database
-- ---------------------------------------------------------------------
-- In SQLite a database is simply ONE FILE. There is no server to
-- install: the file is created the first time you open it.
--
--   Our file:  library_dw.db   (in this folder)
--
-- It holds three groups of tables, kept apart by their name prefix:
--   stg_*  / map_* / etl_*  : STAGING AREA (raw data, cleansing rules, ETL logs)
--   dim_*  / fact_*         : the DATA WAREHOUSE (galaxy schema)
--   sec_*  / audit_log      : SECURITY and AUDIT (scripts 06 and 07)
--
-- HOW TO RUN (any one of these)
--   a) python build_database.py              (runs scripts 01-07 for you)
--   b) DB Browser for SQLite: New Database -> library_dw.db ->
--      tab "Execute SQL" -> open this file -> Execute all (F5)
--   c) command line: sqlite3 library_dw.db < 01_create_database.sql
-- =====================================================================

-- Foreign keys are OFF by default in SQLite. Turn them ON so the
-- database refuses facts that point to a missing dimension row.
-- (This setting must be repeated on every new connection.)
PRAGMA foreign_keys = ON;

-- Normal (rollback) journal mode: simple, and lets read-only users open
-- the file safely. (Analysts and department heads connect read-only.)
PRAGMA journal_mode = DELETE;

-- ---------------------------------------------------------------------
-- Reset: remove old objects so the build always starts clean.
-- Order matters: views and facts first, then the tables they point to.
-- ---------------------------------------------------------------------
DROP VIEW  IF EXISTS v_audit_report;
DROP VIEW  IF EXISTS v_dept_monthly_summary;
DROP VIEW  IF EXISTS v_dept_room_bookings;
DROP VIEW  IF EXISTS v_dept_digital_usage;
DROP VIEW  IF EXISTS v_dept_book_loans;
DROP VIEW  IF EXISTS v_dim_student_masked;
DROP VIEW  IF EXISTS v_usage_cube;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS sec_users;
DROP TABLE IF EXISTS sec_role_permissions;
DROP TABLE IF EXISTS sec_roles;
DROP TABLE IF EXISTS fact_book_loan;
DROP TABLE IF EXISTS fact_digital_usage;
DROP TABLE IF EXISTS fact_room_booking;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_department;
DROP TABLE IF EXISTS dim_student;
DROP TABLE IF EXISTS dim_book;
DROP TABLE IF EXISTS dim_resource;
DROP TABLE IF EXISTS dim_user_type;
DROP TABLE IF EXISTS dim_room;
DROP TABLE IF EXISTS dim_time_slot;
DROP TABLE IF EXISTS dim_booking_purpose;
DROP TABLE IF EXISTS stg_book_transactions;
DROP TABLE IF EXISTS stg_digital_usage;
DROP TABLE IF EXISTS stg_room_bookings;
DROP TABLE IF EXISTS stg_student_master;
DROP TABLE IF EXISTS stg_book_catalog;
DROP TABLE IF EXISTS map_department;
DROP TABLE IF EXISTS map_room;
DROP TABLE IF EXISTS map_time_slot;
DROP TABLE IF EXISTS etl_error_log;
DROP TABLE IF EXISTS etl_batch_log;

-- Show the SQLite version (window functions need 3.25+, math functions 3.35+)
SELECT sqlite_version() AS sqlite_version;
