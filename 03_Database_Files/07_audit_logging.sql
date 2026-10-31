-- =====================================================================
-- Script 07: AUDIT LOGGING - who changed what, and who read what
-- (SQLite 3)
-- ---------------------------------------------------------------------
--   A. audit_log table
--   B. TRIGGERS: every UPDATE or DELETE of student data or facts is
--      recorded automatically (a trigger = SQL that runs by itself
--      when a row changes)
--   C. Every QUERY made through secure_access.py (allowed or denied)
--      and every LOGIN attempt is written to audit_log by that program.
--
--   While an ETL batch is RUNNING (etl_batch_log.status = 'RUNNING'),
--   the triggers stay quiet: the full reload changes thousands of rows
--   and is already recorded in etl_batch_log.
-- =====================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    db_user      TEXT NOT NULL DEFAULT 'direct database access',   -- who
    user_role    TEXT,
    action       TEXT NOT NULL,     -- LOGIN_OK, LOGIN_FAILED, QUERY, DENIED, UPDATE, DELETE
    object_name  TEXT,              -- table / view
    record_key   TEXT,              -- which row
    details      TEXT,              -- old -> new values, or the SQL text
    rows_returned INTEGER
);

CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log (event_time);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log (db_user);

-- ---------------------------------------------------------------------
-- B. Triggers on sensitive data
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_dim_student_update;
CREATE TRIGGER trg_dim_student_update
AFTER UPDATE ON dim_student
WHEN NOT EXISTS (SELECT 1 FROM etl_batch_log WHERE status = 'RUNNING')
BEGIN
    INSERT INTO audit_log (action, object_name, record_key, details)
    VALUES ('UPDATE', 'dim_student', OLD.student_key,
            'level: ' || OLD.student_level || ' -> ' || NEW.student_level ||
            '; department: ' || OLD.home_department_code || ' -> ' || NEW.home_department_code ||
            '; valid_to: ' || OLD.valid_to || ' -> ' || NEW.valid_to);
END;

DROP TRIGGER IF EXISTS trg_dim_student_delete;
CREATE TRIGGER trg_dim_student_delete
AFTER DELETE ON dim_student
WHEN NOT EXISTS (SELECT 1 FROM etl_batch_log WHERE status = 'RUNNING')
BEGIN
    INSERT INTO audit_log (action, object_name, record_key, details)
    VALUES ('DELETE', 'dim_student', OLD.student_key, 'deleted student ' || OLD.student_id_masked);
END;

DROP TRIGGER IF EXISTS trg_fact_loan_update;
CREATE TRIGGER trg_fact_loan_update
AFTER UPDATE ON fact_book_loan
WHEN NOT EXISTS (SELECT 1 FROM etl_batch_log WHERE status = 'RUNNING')
BEGIN
    INSERT INTO audit_log (action, object_name, record_key, details)
    VALUES ('UPDATE', 'fact_book_loan', OLD.transaction_id,
            'duration: ' || IFNULL(OLD.loan_duration_days, 'NULL') || ' -> ' ||
            IFNULL(NEW.loan_duration_days, 'NULL'));
END;

DROP TRIGGER IF EXISTS trg_fact_loan_delete;
CREATE TRIGGER trg_fact_loan_delete
AFTER DELETE ON fact_book_loan
WHEN NOT EXISTS (SELECT 1 FROM etl_batch_log WHERE status = 'RUNNING')
BEGIN
    INSERT INTO audit_log (action, object_name, record_key, details)
    VALUES ('DELETE', 'fact_book_loan', OLD.transaction_id, 'loan row deleted');
END;

DROP TRIGGER IF EXISTS trg_fact_booking_delete;
CREATE TRIGGER trg_fact_booking_delete
AFTER DELETE ON fact_room_booking
WHEN NOT EXISTS (SELECT 1 FROM etl_batch_log WHERE status = 'RUNNING')
BEGIN
    INSERT INTO audit_log (action, object_name, record_key, details)
    VALUES ('DELETE', 'fact_room_booking', OLD.booking_id, 'booking row deleted');
END;

-- ---------------------------------------------------------------------
-- Readable audit report: newest first
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_audit_report;
CREATE VIEW v_audit_report AS
SELECT event_time, db_user, user_role, action, object_name, record_key,
       substr(details, 1, 120) AS details, rows_returned
FROM audit_log
ORDER BY audit_id DESC;

-- =====================================================================
-- TEST (after the warehouse is loaded): change a row and change it back
-- =====================================================================
-- UPDATE dim_student SET valid_to = '9999-12-30' WHERE student_key = 2;
-- UPDATE dim_student SET valid_to = '9999-12-31' WHERE student_key = 2;
-- SELECT * FROM v_audit_report LIMIT 5;          -- 2 new UPDATE rows
