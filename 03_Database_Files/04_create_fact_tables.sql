-- =====================================================================
-- Script 04: FACT tables + the OLAP cube view           (SQLite 3)
-- ---------------------------------------------------------------------
-- GALAXY SCHEMA (also called "fact constellation"):
-- three fact tables, one per library service, that SHARE the conformed
-- dimensions dim_date and dim_department (and dim_student). Sharing them
-- lets us compare books vs downloads vs rooms in one report.
--
-- Why three facts and not one "library_usage_fact"?
--   Each service measures different things at a different GRAIN:
--     loan     -> loan_duration_days, is_overdue     (1 row per checkout)
--     download -> download_count, duration_minutes  (1 row per record of the Excel file)
--     booking  -> duration_hours, time slot, room   (1 row per booking)
--   One table would be full of empty (NULL) columns.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- FACT 1: fact_book_loan        grain: one row = one book checkout
-- ---------------------------------------------------------------------
CREATE TABLE fact_book_loan (
    loan_key            INTEGER PRIMARY KEY,
    transaction_id      INTEGER NOT NULL UNIQUE,              -- source ID: no duplicate loads
    checkout_date_key   INTEGER NOT NULL REFERENCES dim_date (date_key),
    return_date_key     INTEGER NOT NULL DEFAULT -1 REFERENCES dim_date (date_key),  -- -1 = not returned
    student_key         INTEGER NOT NULL REFERENCES dim_student (student_key),
    department_key      INTEGER NOT NULL REFERENCES dim_department (department_key),
    book_key            INTEGER NOT NULL REFERENCES dim_book (book_key),
    -- measures
    loan_count          INTEGER NOT NULL DEFAULT 1,           -- always 1: SUM() = number of loans
    loan_duration_days  INTEGER CHECK (loan_duration_days IS NULL OR loan_duration_days >= 0),
    is_returned         INTEGER NOT NULL CHECK (is_returned IN (0, 1)),
    is_overdue          INTEGER NOT NULL DEFAULT 0 CHECK (is_overdue IN (0, 1)),   -- kept > 21 days (loan period)
    -- audit
    etl_batch_id        INTEGER,
    loaded_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- FACT 2: fact_digital_usage
-- grain: downloads of one resource, by one user type, from one faculty,
--        on one day (= one cleaned row of digital_usage.xlsx)
-- ---------------------------------------------------------------------
CREATE TABLE fact_digital_usage (
    usage_key            INTEGER PRIMARY KEY,
    date_key             INTEGER NOT NULL REFERENCES dim_date (date_key),
    department_key       INTEGER NOT NULL REFERENCES dim_department (department_key),
    user_type_key        INTEGER NOT NULL REFERENCES dim_user_type (user_type_key),
    resource_key         INTEGER NOT NULL REFERENCES dim_resource (resource_key),
    -- measures
    download_count       INTEGER NOT NULL CHECK (download_count >= 0),
    duration_minutes     INTEGER CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
    duration_is_missing  INTEGER NOT NULL DEFAULT 0 CHECK (duration_is_missing IN (0, 1)),
    -- audit
    etl_batch_id         INTEGER,
    loaded_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- FACT 3: fact_room_booking     grain: one row = one booking
-- ---------------------------------------------------------------------
CREATE TABLE fact_room_booking (
    booking_key         INTEGER PRIMARY KEY,
    booking_id          INTEGER NOT NULL UNIQUE,              -- source ID
    date_key            INTEGER NOT NULL REFERENCES dim_date (date_key),
    time_slot_key       INTEGER NOT NULL REFERENCES dim_time_slot (time_slot_key),
    room_key            INTEGER NOT NULL REFERENCES dim_room (room_key),
    student_key         INTEGER NOT NULL REFERENCES dim_student (student_key),     -- 1 = walk-in
    department_key      INTEGER NOT NULL REFERENCES dim_department (department_key),
    purpose_key         INTEGER NOT NULL REFERENCES dim_booking_purpose (purpose_key),
    -- measures
    booking_count       INTEGER NOT NULL DEFAULT 1,
    duration_hours      REAL    NOT NULL CHECK (duration_hours > 0 AND duration_hours <= 12),
    is_walk_in          INTEGER NOT NULL DEFAULT 0 CHECK (is_walk_in IN (0, 1)),
    -- audit
    etl_batch_id        INTEGER,
    loaded_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- business rule: a room cannot be booked twice in the same slot on the same day
    UNIQUE (room_key, date_key, time_slot_key)
);

-- ---------------------------------------------------------------------
-- OLAP CUBE VIEW: the three facts stacked on the shared dimensions
-- (date + department) with a "service" column. Used by the business
-- queries, the security views and Power BI.
--   Book Loans = 1 per checkout, Digital Downloads = number of downloads,
--   Room Bookings = 1 per booking
-- ---------------------------------------------------------------------
CREATE VIEW v_usage_cube AS
SELECT checkout_date_key AS date_key, department_key, student_key,
       'Book Loans' AS service, loan_count AS usage_count
FROM fact_book_loan
UNION ALL
SELECT date_key, department_key, NULL AS student_key,
       'Digital Downloads', download_count
FROM fact_digital_usage
UNION ALL
SELECT date_key, department_key, student_key,
       'Room Bookings', booking_count
FROM fact_room_booking;
