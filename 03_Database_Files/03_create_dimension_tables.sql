-- =====================================================================
-- Script 03: DIMENSION tables                          (SQLite 3)
-- ---------------------------------------------------------------------
-- Dimensions answer "WHO, WHAT, WHERE, WHEN" for every fact.
-- Conventions:
--   * Every dimension has an integer SURROGATE KEY (xxx_key) created by
--     the warehouse - never taken from a source system - so the warehouse
--     is safe when a source changes its ID format.
--   * The source identifier is kept as the NATURAL KEY (e.g. student_id).
--   * Key 1 is always an "Unknown" row, so facts never point to NULL
--     (e.g. a walk-in room booking without StudentID -> Unknown student).
--   * SQLite has no BOOLEAN type: we store 1 = true, 0 = false.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. dim_date  (shared by ALL fact tables = "conformed dimension")
--    Solves the "different date formats" problem: the ETL converts every
--    date to ISO 8601 (YYYY-MM-DD) and all facts point to this table.
--    date_key = YYYYMMDD as a number (20240115): readable and sortable.
-- ---------------------------------------------------------------------
CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,           -- 20240115
    full_date       TEXT    NOT NULL UNIQUE,       -- '2024-01-15'
    day_of_month    INTEGER NOT NULL,              -- 15
    day_name        TEXT    NOT NULL,              -- 'Monday'
    day_of_week     INTEGER NOT NULL,              -- 1 = Monday ... 7 = Sunday
    is_weekend      INTEGER NOT NULL,              -- 1 / 0
    week_of_year    INTEGER NOT NULL,              -- 0-53 (weeks start on Monday)
    week_start_date TEXT    NOT NULL,              -- Monday of that week
    month_num       INTEGER NOT NULL,              -- 1
    month_name      TEXT    NOT NULL,              -- 'January'
    month_short     TEXT    NOT NULL,              -- 'Jan'
    month_label     TEXT    NOT NULL,              -- '2024-01'
    quarter_num     INTEGER NOT NULL,              -- 1
    quarter_name    TEXT    NOT NULL,              -- 'Q1'
    year_num        INTEGER NOT NULL,              -- 2024
    academic_year   TEXT    NOT NULL,              -- '2023/2024' (starts in September)
    semester        TEXT    NOT NULL               -- 'Semester 1' / 'Semester 2' / 'Break'
);

-- Special row for "no date" (a book that is not returned yet)
INSERT INTO dim_date VALUES
 (-1, '1900-01-01', 0, 'N/A', 0, 0, 0, '1900-01-01', 0, 'N/A', 'N/A',
  'N/A', 0, 'NA', 0, 'N/A', 'N/A');

-- One row per day, 2023-01-01 to 2027-12-31, made with a RECURSIVE query:
-- start with the first day, then keep adding 1 day until the last day.
INSERT INTO dim_date
WITH RECURSIVE days(dt) AS (
    SELECT '2023-01-01'
    UNION ALL
    SELECT date(dt, '+1 day') FROM days WHERE dt < '2027-12-31'
),
parts AS (
    SELECT dt,
           CAST(strftime('%m', dt) AS INTEGER)               AS m,
           CAST(strftime('%Y', dt) AS INTEGER)               AS y,
           (CAST(strftime('%w', dt) AS INTEGER) + 6) % 7 + 1 AS dow   -- %w: 0 = Sunday -> make Monday = 1
    FROM days
)
SELECT
    CAST(strftime('%Y%m%d', dt) AS INTEGER),                         -- date_key
    dt,                                                              -- full_date
    CAST(strftime('%d', dt) AS INTEGER),                             -- day_of_month
    CASE dow WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday' WHEN 3 THEN 'Wednesday'
             WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday' WHEN 6 THEN 'Saturday'
             ELSE 'Sunday' END,                                      -- day_name
    dow,                                                             -- day_of_week
    CASE WHEN dow >= 6 THEN 1 ELSE 0 END,                            -- is_weekend
    CAST(strftime('%W', dt) AS INTEGER),                             -- week_of_year
    date(dt, '-' || (dow - 1) || ' days'),                           -- week_start_date
    m,                                                               -- month_num
    CASE m WHEN 1 THEN 'January' WHEN 2 THEN 'February' WHEN 3 THEN 'March'
           WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June'
           WHEN 7 THEN 'July' WHEN 8 THEN 'August' WHEN 9 THEN 'September'
           WHEN 10 THEN 'October' WHEN 11 THEN 'November' ELSE 'December' END,
    CASE m WHEN 1 THEN 'Jan' WHEN 2 THEN 'Feb' WHEN 3 THEN 'Mar' WHEN 4 THEN 'Apr'
           WHEN 5 THEN 'May' WHEN 6 THEN 'Jun' WHEN 7 THEN 'Jul' WHEN 8 THEN 'Aug'
           WHEN 9 THEN 'Sep' WHEN 10 THEN 'Oct' WHEN 11 THEN 'Nov' ELSE 'Dec' END,
    strftime('%Y-%m', dt),                                           -- month_label
    (m + 2) / 3,                                                     -- quarter_num
    'Q' || ((m + 2) / 3),                                            -- quarter_name
    y,                                                               -- year_num
    CASE WHEN m >= 9 THEN y || '/' || (y + 1) ELSE (y - 1) || '/' || y END,   -- academic_year
    CASE WHEN m IN (9, 10, 11, 12, 1) THEN 'Semester 1'
         WHEN m IN (2, 3, 4, 5, 6)    THEN 'Semester 2'
         ELSE 'Break' END                                            -- semester
FROM parts;

-- ---------------------------------------------------------------------
-- 2. dim_department  (shared by all facts - conformed dimension)
--    "CS", "Computer Science", "CompSci" all end up as ONE row here.
-- ---------------------------------------------------------------------
CREATE TABLE dim_department (
    department_key   INTEGER PRIMARY KEY,
    department_code  TEXT NOT NULL UNIQUE,     -- 'CS'
    department_name  TEXT NOT NULL,            -- 'Computer Science'
    faculty_name     TEXT NOT NULL
);

INSERT INTO dim_department (department_key, department_code, department_name, faculty_name) VALUES
 (1, 'UNK', 'Unknown',           'Unknown'),
 (2, 'CS',  'Computer Science',  'Faculty of Computing & IT'),
 (3, 'ENG', 'Engineering',       'Faculty of Engineering & Technology'),
 (4, 'BUS', 'Business',          'Faculty of Business & Economics'),
 (5, 'MED', 'Health Sciences',   'Faculty of Medicine & Health Sciences'),
 (6, 'EDU', 'Education',         'Faculty of Education'),
 (7, 'LAW', 'Law',               'Faculty of Law'),
 (8, 'ART', 'Arts & Humanities', 'Faculty of Arts & Social Sciences'),
 (9, 'SCI', 'Natural Sciences',  'Faculty of Science');

-- ---------------------------------------------------------------------
-- 3. dim_student
--    StudentID is personal data, so a MASKED copy is stored as well
--    (STU-****-001). Reports use only the masked one (see script 06).
--    valid_from / valid_to / is_current = SCD Type 2 columns: they keep
--    history if a student changes department or level.
-- ---------------------------------------------------------------------
CREATE TABLE dim_student (
    student_key          INTEGER PRIMARY KEY,
    student_id           TEXT    NOT NULL,     -- 'STU-2024-001' (natural key)
    student_id_masked    TEXT    NOT NULL,     -- 'STU-****-001'
    student_level        TEXT    NOT NULL,     -- Undergraduate / Graduate / Unknown
    year_of_study        INTEGER,
    gender               TEXT,
    home_department_code TEXT    NOT NULL,
    valid_from           TEXT    NOT NULL DEFAULT '2000-01-01',
    valid_to             TEXT    NOT NULL DEFAULT '9999-12-31',
    is_current           INTEGER NOT NULL DEFAULT 1
);

INSERT INTO dim_student (student_key, student_id, student_id_masked, student_level,
                         year_of_study, gender, home_department_code)
VALUES (1, 'UNKNOWN', 'UNKNOWN', 'Unknown', NULL, NULL, 'UNK');      -- walk-ins

-- ---------------------------------------------------------------------
-- 4. dim_book  (physical books: lending system + catalogue)
-- ---------------------------------------------------------------------
CREATE TABLE dim_book (
    book_key          INTEGER PRIMARY KEY,
    isbn              TEXT NOT NULL UNIQUE,    -- '978-0134685991'
    title             TEXT NOT NULL,
    author            TEXT,
    publisher         TEXT,
    publication_year  INTEGER,
    book_category     TEXT NOT NULL            -- Textbook / Reference / Fiction / Research
);

INSERT INTO dim_book (book_key, isbn, title, book_category)
VALUES (1, 'UNKNOWN', 'Unknown Book', 'Unknown');

-- ---------------------------------------------------------------------
-- 5. dim_resource  (digital resources)  "E-book" / "e-Book" -> 'E-book'
-- ---------------------------------------------------------------------
CREATE TABLE dim_resource (
    resource_key      INTEGER PRIMARY KEY,
    resource_title    TEXT NOT NULL,
    resource_type     TEXT NOT NULL,           -- E-book / Journal / Article
    UNIQUE (resource_title, resource_type)
);

INSERT INTO dim_resource (resource_key, resource_title, resource_type)
VALUES (1, 'Unknown Resource', 'Unknown');

-- ---------------------------------------------------------------------
-- 6. dim_user_type  (who downloaded - the digital source has no StudentID)
-- ---------------------------------------------------------------------
CREATE TABLE dim_user_type (
    user_type_key     INTEGER PRIMARY KEY,
    user_type         TEXT NOT NULL UNIQUE,    -- 'Undergraduate Student' ...
    user_group        TEXT NOT NULL,           -- Student / Employee
    student_level     TEXT NOT NULL            -- Undergraduate / Graduate / N/A
);

INSERT INTO dim_user_type (user_type_key, user_type, user_group, student_level) VALUES
 (1, 'Unknown',               'Unknown',  'Unknown'),
 (2, 'Undergraduate Student', 'Student',  'Undergraduate'),
 (3, 'Graduate Student',      'Student',  'Graduate'),
 (4, 'Faculty',               'Employee', 'N/A'),
 (5, 'Staff',                 'Employee', 'N/A');

-- ---------------------------------------------------------------------
-- 7. dim_room  ("R101", "R-101", "Room101" -> 'R101')
--    Room features help answer "which rooms are popular and WHY?"
-- ---------------------------------------------------------------------
CREATE TABLE dim_room (
    room_key          INTEGER PRIMARY KEY,
    room_number       TEXT    NOT NULL UNIQUE,
    floor_num         INTEGER NOT NULL,
    capacity          INTEGER NOT NULL,        -- seats
    room_type         TEXT    NOT NULL,        -- Individual / Group / Seminar
    has_projector     INTEGER NOT NULL DEFAULT 0,
    has_whiteboard    INTEGER NOT NULL DEFAULT 0,
    is_quiet_zone     INTEGER NOT NULL DEFAULT 0
);

INSERT INTO dim_room (room_key, room_number, floor_num, capacity, room_type,
                      has_projector, has_whiteboard, is_quiet_zone) VALUES
 (1,  'UNKNOWN', 0, 0,  'Unknown',    0, 0, 0),
 (2,  'R101',    1, 4,  'Group',      0, 1, 0),
 (3,  'R102',    1, 6,  'Group',      1, 1, 0),
 (4,  'R103',    1, 2,  'Individual', 0, 0, 1),
 (5,  'R104',    1, 2,  'Individual', 0, 0, 1),
 (6,  'R201',    2, 8,  'Group',      1, 1, 0),
 (7,  'R202',    2, 4,  'Group',      0, 1, 0),
 (8,  'R203',    2, 1,  'Individual', 0, 0, 1),
 (9,  'R204',    2, 12, 'Seminar',    1, 1, 0),
 (10, 'R301',    3, 6,  'Group',      1, 1, 0),
 (11, 'R302',    3, 20, 'Seminar',    1, 1, 0),
 (12, 'R303',    3, 1,  'Individual', 0, 0, 1);

-- ---------------------------------------------------------------------
-- 8. dim_time_slot  ("Morning", "8AM-10AM", "AM" -> standard 2-hour blocks)
-- ---------------------------------------------------------------------
CREATE TABLE dim_time_slot (
    time_slot_key     INTEGER PRIMARY KEY,
    slot_code         TEXT    NOT NULL UNIQUE, -- '08-10'
    slot_label        TEXT    NOT NULL,        -- '08:00 - 10:00'
    start_hour        INTEGER NOT NULL,
    end_hour          INTEGER NOT NULL,
    day_period        TEXT    NOT NULL         -- Morning / Afternoon / Evening
);

INSERT INTO dim_time_slot (time_slot_key, slot_code, slot_label, start_hour, end_hour, day_period) VALUES
 (1, 'UNK',   'Unknown',       0,  0,  'Unknown'),
 (2, '08-10', '08:00 - 10:00', 8,  10, 'Morning'),
 (3, '10-12', '10:00 - 12:00', 10, 12, 'Morning'),
 (4, '12-14', '12:00 - 14:00', 12, 14, 'Afternoon'),
 (5, '14-16', '14:00 - 16:00', 14, 16, 'Afternoon'),
 (6, '16-18', '16:00 - 18:00', 16, 18, 'Afternoon'),
 (7, '18-20', '18:00 - 20:00', 18, 20, 'Evening');

-- ---------------------------------------------------------------------
-- 9. dim_booking_purpose
-- ---------------------------------------------------------------------
CREATE TABLE dim_booking_purpose (
    purpose_key       INTEGER PRIMARY KEY,
    purpose_name      TEXT NOT NULL UNIQUE,
    purpose_group     TEXT NOT NULL            -- Individual / Collaborative
);

INSERT INTO dim_booking_purpose (purpose_key, purpose_name, purpose_group) VALUES
 (1, 'Unknown',          'Unknown'),
 (2, 'Study',            'Individual'),
 (3, 'Exam Preparation', 'Individual'),
 (4, 'Research',         'Individual'),
 (5, 'Group Project',    'Collaborative'),
 (6, 'Meeting',          'Collaborative'),
 (7, 'Tutorial',         'Collaborative');
