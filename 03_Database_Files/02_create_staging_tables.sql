-- =====================================================================
-- Script 02: STAGING AREA tables                       (SQLite 3)
-- ---------------------------------------------------------------------
-- Rule of the staging area: store the source data EXACTLY as it arrives.
-- Every source column is TEXT, so bad values such as "Jan 15, 2024",
-- "2 hrs" or "R-101" never make the load fail. The ETL cleans the data
-- afterwards, and only valid rows move on to the warehouse.
--
-- Audit columns on every staging table:
--   batch_id    : which ETL run loaded the row
--   source_file : file the row came from
--   row_num     : original line number (to trace an error back to the file)
--   loaded_at   : when the row was staged
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- ETL control: one row per ETL run
-- ---------------------------------------------------------------------
CREATE TABLE etl_batch_log (
    batch_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    load_type       TEXT    NOT NULL CHECK (load_type IN ('FULL', 'INCREMENTAL')),
    started_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     TEXT,
    status          TEXT    NOT NULL DEFAULT 'RUNNING'
                            CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    rows_extracted  INTEGER DEFAULT 0,
    rows_loaded     INTEGER DEFAULT 0,
    rows_rejected   INTEGER DEFAULT 0,
    notes           TEXT
);

-- ---------------------------------------------------------------------
-- Source 1: Book Lending System (export of the book_transactions table)
-- ---------------------------------------------------------------------
CREATE TABLE stg_book_transactions (
    stg_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    TransactionID   TEXT,
    StudentID       TEXT,
    BookISBN        TEXT,
    CheckoutDate    TEXT,
    ReturnDate      TEXT,
    Department      TEXT,
    BookCategory    TEXT,
    batch_id        INTEGER,
    source_file     TEXT,
    row_num         INTEGER,
    loaded_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Source 2: Digital Resources System (digital_usage.xlsx, 3 sheets)
-- ResourceTitle is needed for "Top 10 downloaded journals" (Q4).
-- ---------------------------------------------------------------------
CREATE TABLE stg_digital_usage (
    stg_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    "Date"            TEXT,
    UserType          TEXT,
    ResourceType      TEXT,
    ResourceTitle     TEXT,
    Faculty           TEXT,
    DownloadCount     TEXT,
    Duration_Minutes  TEXT,
    source_sheet      TEXT,
    batch_id          INTEGER,
    source_file       TEXT,
    row_num           INTEGER,
    loaded_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Source 3: Study Room Booking System (room_bookings.csv)
-- ---------------------------------------------------------------------
CREATE TABLE stg_room_bookings (
    stg_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    BookingID       TEXT,
    RoomNumber      TEXT,
    BookingDate     TEXT,
    TimeSlot        TEXT,
    StudentID       TEXT,
    DurationHours   TEXT,
    Purpose         TEXT,
    batch_id        INTEGER,
    source_file     TEXT,
    row_num         INTEGER,
    loaded_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Reference data: student master (Registrar) and book catalogue.
-- The student master fills missing departments and gives the
-- Undergraduate / Graduate level.
-- ---------------------------------------------------------------------
CREATE TABLE stg_student_master (
    stg_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    StudentID       TEXT,
    Department      TEXT,
    StudentLevel    TEXT,
    YearOfStudy     TEXT,
    Gender          TEXT,
    batch_id        INTEGER,
    source_file     TEXT,
    loaded_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE stg_book_catalog (
    stg_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    BookISBN        TEXT,
    Title           TEXT,
    Author          TEXT,
    Publisher       TEXT,
    PublicationYear TEXT,
    BookCategory    TEXT,
    batch_id        INTEGER,
    source_file     TEXT,
    loaded_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- MAPPING (lookup) TABLES - the cleansing rules stored as data.
-- The ETL compares in lower case, so 'CompSci' and 'compsci' both match.
-- =====================================================================
CREATE TABLE map_department (
    raw_value        TEXT PRIMARY KEY,          -- e.g. 'compsci', 'engr'
    department_code  TEXT NOT NULL              -- e.g. 'CS', 'ENG'
);

INSERT INTO map_department (raw_value, department_code) VALUES
 ('cs','CS'), ('computer science','CS'), ('compsci','CS'), ('comp sci','CS'),
 ('eng','ENG'), ('engineering','ENG'), ('engr','ENG'), ('eng.','ENG'),
 ('bus','BUS'), ('business','BUS'), ('business admin','BUS'), ('bus. admin','BUS'),
 ('med','MED'), ('medicine','MED'), ('health sciences','MED'),
 ('edu','EDU'), ('education','EDU'), ('educ','EDU'),
 ('law','LAW'),
 ('art','ART'), ('arts','ART'), ('arts & humanities','ART'), ('humanities','ART'),
 ('sci','SCI'), ('science','SCI'), ('natural sciences','SCI'), ('sciences','SCI');

CREATE TABLE map_room (
    raw_pattern      TEXT PRIMARY KEY,          -- e.g. 'R-101', 'Room101', 'Room 101'
    rule             TEXT NOT NULL              -- how the ETL turns it into 'R101'
);

INSERT INTO map_room (raw_pattern, rule) VALUES
 ('R101 / r101',        'upper case R + digits'),
 ('R-101',              'remove the dash'),
 ('Room101 / Room 101', 'replace "Room" with "R", remove spaces');

CREATE TABLE map_time_slot (
    raw_value        TEXT PRIMARY KEY,          -- e.g. 'morning', '8am-10am', 'am'
    slot_code        TEXT NOT NULL              -- e.g. '08-10'
);

INSERT INTO map_time_slot (raw_value, slot_code) VALUES
 ('8am-10am','08-10'), ('08:00-10:00','08-10'), ('morning','08-10'), ('am','08-10'),
 ('10am-12pm','10-12'), ('10:00-12:00','10-12'), ('late morning','10-12'),
 ('12pm-2pm','12-14'), ('12:00-14:00','12-14'), ('midday','12-14'), ('noon','12-14'),
 ('2pm-4pm','14-16'), ('14:00-16:00','14-16'), ('afternoon','14-16'), ('pm','14-16'),
 ('4pm-6pm','16-18'), ('16:00-18:00','16-18'), ('late afternoon','16-18'),
 ('6pm-8pm','18-20'), ('18:00-20:00','18-20'), ('evening','18-20');

-- =====================================================================
-- ERROR LOG - every rejected or corrected value is recorded here
-- =====================================================================
CREATE TABLE etl_error_log (
    error_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER,
    source_table    TEXT NOT NULL,
    source_row_num  INTEGER,
    column_name     TEXT,
    bad_value       TEXT,
    error_type      TEXT NOT NULL,     -- INVALID_DATE, DUPLICATE_EXACT, MISSING_VALUE ...
    action_taken    TEXT NOT NULL,     -- REJECTED, CORRECTED, DEFAULTED
    message         TEXT,
    logged_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_err_batch ON etl_error_log (batch_id);
CREATE INDEX idx_err_type  ON etl_error_log (error_type);
