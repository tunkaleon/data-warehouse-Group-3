"""
=====================================================================
 etl_script.py  -  University Library Analytics Data Warehouse
=====================================================================
 ETL = Extract  ->  Transform  ->  Load

   EXTRACT   : read the 3 source files (+ 2 reference files) exactly as
               they are, every value as TEXT, into the STAGING AREA.
   TRANSFORM : clean the data (dates, names, duplicates, missing values,
               numbers stored as text) and record every problem in an
               ERROR LOG.
   LOAD      : build the dimension and fact tables, write them to
               sample_data.sql and load them into the SQLite database
               ../03_Database_Files/library_dw.db

 We chose ETL (clean BEFORE loading) and not ELT, because the data is
 small and the cleaning rules are easier to write and test in Python.

 HOW TO RUN (from the 04_ETL_Files folder)
     pip install pandas openpyxl        (only once; SQLite is built into Python)
     python etl_script.py               -> cleans the data and loads library_dw.db
                                           (creates the database first if it is missing)

 FILES CREATED
     ../03_Database_Files/library_dw.db     the loaded SQLite data warehouse
     ../03_Database_Files/sample_data.sql   the same data as INSERT statements (staging + warehouse)
     ../06_Dashboards/PowerBI_Data/*.csv    clean tables for Power BI (StudentID masked)
     output/etl_error_log.csv               every problem found
     output/quality_metrics.json            before/after numbers for the quality report
     error_log_sample.txt                   readable summary of the error log
=====================================================================
"""

import os
import re
import sys
import json
import sqlite3
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

# =====================================================================
# PART 0. SETTINGS
# =====================================================================
HERE = os.path.dirname(os.path.abspath(__file__))           # .../04_ETL_Files
PROJECT = os.path.dirname(HERE)                             # project root folder
SOURCE_DIR = os.path.join(PROJECT, "09_Source_Data")
OUTPUT_DIR = os.path.join(HERE, "output")
CSV_DIR = os.path.join(PROJECT, "06_Dashboards", "PowerBI_Data")   # clean tables for Power BI
DB_DIR = os.path.join(PROJECT, "03_Database_Files")
DB_FILE = os.path.join(DB_DIR, "library_dw.db")            # the SQLite data warehouse
SQL_FILE = os.path.join(DB_DIR, "sample_data.sql")

BATCH_ID = 1                       # number of this ETL run (read from etl_batch_log at start)
LOAD_TYPE = "FULL"                 # FULL = empty the warehouse and reload everything
FIRST_VALID_DATE = date(2023, 1, 1)
LAST_VALID_DATE = date(2025, 12, 31)
OVERDUE_AFTER_DAYS = 21            # library rule: loan period is 21 days; longer = overdue

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CSV_DIR, exist_ok=True)


# =====================================================================
# PART 1. CLEANSING RULES (lookup tables)
# ---------------------------------------------------------------------
# The department and time-slot rules are stored IN THE DATABASE
# (tables map_department and map_time_slot, script 02). The ETL reads
# them at start-up (see load_cleansing_rules), so a new spelling such as
# "Comp. Science" is fixed by adding ONE ROW - no code change needed.
# Keys are lower case: we lower-case the raw value before the lookup,
# so "CompSci", "compsci" and " COMPSCI " all match.
# The surrogate keys below MUST match the seed rows in
# 03_create_dimension_tables.sql (the ETL checks this at start-up).
# =====================================================================
DEPARTMENT_MAP = {}                # filled from map_department
TIME_SLOT_MAP = {}                 # filled from map_time_slot
DEPARTMENT_KEYS = {"UNK": 1, "CS": 2, "ENG": 3, "BUS": 4, "MED": 5,
                   "EDU": 6, "LAW": 7, "ART": 8, "SCI": 9}

TIME_SLOT_KEYS = {"UNK": 1, "08-10": 2, "10-12": 3, "12-14": 4, "14-16": 5, "16-18": 6, "18-20": 7}

ROOM_KEYS = {"UNKNOWN": 1, "R101": 2, "R102": 3, "R103": 4, "R104": 5, "R201": 6, "R202": 7,
             "R203": 8, "R204": 9, "R301": 10, "R302": 11, "R303": 12}

RESOURCE_TYPE_MAP = {"e-book": "E-book", "ebook": "E-book", "journal": "Journal", "article": "Article"}

USER_TYPE_MAP = {
    "student": "Undergraduate Student", "undergraduate": "Undergraduate Student",
    "ug student": "Undergraduate Student",
    "grad student": "Graduate Student", "graduate": "Graduate Student",
    "postgraduate": "Graduate Student",
    "faculty": "Faculty", "lecturer": "Faculty",
    "staff": "Staff",
}
USER_TYPE_KEYS = {"Unknown": 1, "Undergraduate Student": 2, "Graduate Student": 3,
                  "Faculty": 4, "Staff": 5}

PURPOSE_MAP = {"study": "Study", "group project": "Group Project", "meeting": "Meeting",
               "exam preparation": "Exam Preparation", "exam prep": "Exam Preparation",
               "research": "Research", "tutorial": "Tutorial"}
PURPOSE_KEYS = {"Unknown": 1, "Study": 2, "Exam Preparation": 3, "Research": 4,
                "Group Project": 5, "Meeting": 6, "Tutorial": 7}

# Date formats each source may contain (tried one after the other)
BOOK_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y"]
ROOM_DATE_FORMATS = ["%Y-%m-%d", "%d-%b-%Y"]
# The Excel file uses ONE known format per sheet (found by profiling the data).
# "2024-05-03" is ambiguous, so we must use the sheet's own rule.
DIGITAL_SHEET_FORMATS = {"Usage_2023": "%m/%d/%Y", "Usage_2024": "%Y-%d-%m", "Usage_2025": "%b %d, %Y"}


# =====================================================================
# PART 2. ERROR LOG
# Every rejected or corrected value is written here, so the library can
# check WHAT was changed and WHY (requirement: "log transformation errors").
# =====================================================================
error_log = []


def log_error(source, row_num, column, bad_value, error_type, action, message):
    """Add one entry to the error log."""
    error_log.append({
        "error_id": len(error_log) + 1,
        "batch_id": BATCH_ID,
        "source_table": source,
        "source_row_num": row_num,
        "column_name": column,
        "bad_value": "" if bad_value is None else str(bad_value)[:250],
        "error_type": error_type,      # e.g. INVALID_DATE, DUPLICATE_EXACT
        "action_taken": action,        # REJECTED / CORRECTED / DEFAULTED / FLAGGED
        "message": message,
    })


# =====================================================================
# PART 3. SMALL HELPER FUNCTIONS (each one does one cleaning job)
# =====================================================================
def clean_text(value):
    """Remove extra spaces. Empty text becomes None (= NULL)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    value = " ".join(str(value).split())     # "  Comp   Sci " -> "Comp Sci"
    return value if value else None


def parse_date(text, formats):
    """Try each date format until one works. Returns a date, or None if none works."""
    text = clean_text(text)
    if text is None:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass                              # wrong format -> try the next one
    return None


def date_key(d):
    """2024-01-15 -> 20240115 (the key used in dim_date). No date -> -1."""
    return int(d.strftime("%Y%m%d")) if d else -1


def parse_number(text):
    """Turn text like ' 1,203 ', '2 hrs' or '1.5h' into a number. Returns None if impossible."""
    text = clean_text(text)
    if text is None:
        return None
    text = text.replace(",", "").lower()                   # remove thousands separator
    text = re.sub(r"\s*(hrs|hr|h|hours|min|mins)$", "", text)   # remove units
    try:
        return float(text)
    except ValueError:
        return None


def standardize_department(raw):
    """'CompSci' / 'Computer Science' / 'cs' -> 'CS'. Unknown spelling -> None."""
    text = clean_text(raw)
    return DEPARTMENT_MAP.get(text.lower()) if text else None


def standardize_room(raw):
    """'R-101', 'Room101', 'Room 101', 'r101' -> 'R101'."""
    text = clean_text(raw)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)                       # keep only the digits
    room = "R" + digits
    return room if room in ROOM_KEYS else None


def standardize_isbn(raw):
    """'9780134685991' or '978-0134685991' -> '978-0134685991'."""
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits[:3] + "-" + digits[3:] if len(digits) == 13 else None


def mask_student_id(student_id):
    """Data masking: 'STU-2024-001' -> 'STU-****-001' (hides the intake year)."""
    parts = student_id.split("-")
    return f"{parts[0]}-****-{parts[2]}" if len(parts) == 3 else "MASKED"


def date_pattern(text):
    """Describe the SHAPE of a date text (used only for the before/after report)."""
    text = clean_text(text)
    if text is None:
        return "(empty)"
    shape = re.sub(r"[A-Za-z]+", "Mon", re.sub(r"\d", "9", text))
    return shape                                            # e.g. '9999-99-99', '99/99/9999'


# =====================================================================
# PART 4. EXTRACT  (source files -> staging tables, all values as text)
# =====================================================================
def read_csv_as_text(path):
    """Read a CSV keeping every value as text exactly as it is in the file."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    df = df.astype(object).where(df.notna(), None)          # NaN -> None
    df["row_num"] = range(2, len(df) + 2)                   # line 1 is the header
    df["source_file"] = os.path.basename(path)
    return df


def extract():
    print("\n[1/5] EXTRACT - reading source files into the staging area")
    staging = {}
    staging["stg_book_transactions"] = read_csv_as_text(os.path.join(SOURCE_DIR, "book_transactions.csv"))
    staging["stg_room_bookings"] = read_csv_as_text(os.path.join(SOURCE_DIR, "room_bookings.csv"))
    staging["stg_student_master"] = read_csv_as_text(os.path.join(SOURCE_DIR, "reference", "student_master.csv"))
    staging["stg_book_catalog"] = read_csv_as_text(os.path.join(SOURCE_DIR, "reference", "book_catalog.csv"))

    # Excel: read EVERY sheet and stack them into one table
    sheets = pd.read_excel(os.path.join(SOURCE_DIR, "digital_usage.xlsx"), sheet_name=None,
                           dtype=str, keep_default_na=False, na_values=[""])
    parts = []
    for sheet_name, df in sheets.items():
        df = df.astype(object).where(df.notna(), None)
        df["source_sheet"] = sheet_name
        df["row_num"] = range(2, len(df) + 2)
        df["source_file"] = "digital_usage.xlsx"
        parts.append(df)
    staging["stg_digital_usage"] = pd.concat(parts, ignore_index=True)

    for name, df in staging.items():
        print(f"      {name:24s} {len(df):>6} rows")
    return staging


# =====================================================================
# PART 5. TRANSFORM  (one function per source)
# =====================================================================
def remove_exact_duplicates(df, source, id_column):
    """Rows that are 100% identical (same values in every source column) are removed."""
    data_cols = [c for c in df.columns if c not in ("row_num", "source_file")]
    is_dup = df.duplicated(subset=data_cols, keep="first")
    for _, row in df[is_dup].iterrows():
        log_error(source, row["row_num"], id_column, row[id_column], "DUPLICATE_EXACT", "REJECTED",
                  "Identical row already exists (copied twice by the source system)")
    return df[~is_dup].copy(), int(is_dup.sum())


def transform_students(stg):
    """Student master is clean reference data; we only standardise it."""
    students = {}
    for _, r in stg.iterrows():
        sid = clean_text(r["StudentID"])
        students[sid] = {
            "student_id": sid,
            "department_code": standardize_department(r["Department"]) or "UNK",
            "student_level": clean_text(r["StudentLevel"]) or "Unknown",
            "year_of_study": int(r["YearOfStudy"]) if clean_text(r["YearOfStudy"]) else None,
            "gender": clean_text(r["Gender"]),
        }
    return students


def transform_books(stg):
    books = {}
    for _, r in stg.iterrows():
        isbn = standardize_isbn(r["BookISBN"])
        books[isbn] = {
            "isbn": isbn,
            "title": clean_text(r["Title"]),
            "author": clean_text(r["Author"]),
            "publisher": clean_text(r["Publisher"]),
            "publication_year": int(r["PublicationYear"]),
            "book_category": clean_text(r["BookCategory"]).title(),
        }
    return books


def transform_book_transactions(stg, students, books, m):
    src = "stg_book_transactions"
    df, m["exact_duplicates"] = remove_exact_duplicates(stg, src, "TransactionID")
    clean_rows = []

    for _, r in df.iterrows():
        row = r["row_num"]

        # --- TransactionID must be a whole number ---
        try:
            tid = int(r["TransactionID"])
        except (TypeError, ValueError):
            log_error(src, row, "TransactionID", r["TransactionID"], "INVALID_TYPE", "REJECTED", "Not a number")
            continue

        # --- CheckoutDate: convert any format to a real date (ISO 8601) ---
        checkout = parse_date(r["CheckoutDate"], BOOK_DATE_FORMATS)
        if checkout is None or not (FIRST_VALID_DATE <= checkout <= LAST_VALID_DATE):
            log_error(src, row, "CheckoutDate", r["CheckoutDate"], "INVALID_DATE", "REJECTED",
                      "Checkout date is not a valid date in 2023-2025")
            continue

        # --- ReturnDate: empty = book not returned yet (kept, flagged) ---
        returned = parse_date(r["ReturnDate"], BOOK_DATE_FORMATS)
        if clean_text(r["ReturnDate"]) and returned is None:
            log_error(src, row, "ReturnDate", r["ReturnDate"], "INVALID_DATE", "DEFAULTED",
                      "Unreadable return date -> treated as Not Returned")
        if returned and returned < checkout:
            log_error(src, row, "ReturnDate", r["ReturnDate"], "INVALID_RANGE", "REJECTED",
                      f"Return date is before checkout date ({checkout})")
            continue

        # --- Department: standardise; if missing, look it up in the student master ---
        sid = clean_text(r["StudentID"])
        dept = standardize_department(r["Department"])
        if dept is None:
            master = students.get(sid)
            dept = master["department_code"] if master else "UNK"
            log_error(src, row, "Department", r["Department"], "MISSING_VALUE", "CORRECTED",
                      f"Department filled from student master data -> {dept}")

        # --- Student must exist in the master list ---
        if sid not in students:
            log_error(src, row, "StudentID", sid, "UNKNOWN_REFERENCE", "DEFAULTED",
                      "Student not found in master data -> Unknown student")
            sid = None

        # --- ISBN: same format for all; unknown ISBN -> 'Unknown Book' ---
        isbn = standardize_isbn(r["BookISBN"])
        if isbn not in books:
            log_error(src, row, "BookISBN", r["BookISBN"], "UNKNOWN_REFERENCE", "DEFAULTED",
                      "ISBN not in the book catalogue -> Unknown Book")
            isbn = None

        clean_rows.append({
            "transaction_id": tid, "student_id": sid, "isbn": isbn, "row_num": row,
            "checkout_date": checkout, "return_date": returned, "department_code": dept,
        })

    clean = pd.DataFrame(clean_rows)

    # --- Logical duplicates: same student + same book + same day = same loan ---
    clean = clean.sort_values("transaction_id")
    is_dup = clean.duplicated(subset=["student_id", "isbn", "checkout_date"], keep="first")
    for _, r in clean[is_dup].iterrows():
        log_error(src, r["row_num"], "TransactionID", r["transaction_id"], "DUPLICATE_LOGICAL", "REJECTED",
                  "Same student, book and checkout date as an earlier transaction")
    m["logical_duplicates"] = int(is_dup.sum())
    clean = clean[~is_dup]

    # --- New calculated measures ---
    clean["is_returned"] = clean["return_date"].notna()
    clean["loan_duration_days"] = [
        (ret - out).days if ret else None for out, ret in zip(clean["checkout_date"], clean["return_date"])
    ]
    clean["is_overdue"] = [(d is not None and d > OVERDUE_AFTER_DAYS) for d in clean["loan_duration_days"]]
    return clean


def transform_digital_usage(stg, m):
    src = "stg_digital_usage"
    df, m["exact_duplicates"] = remove_exact_duplicates(stg, src, "Date")
    clean_rows = []

    for _, r in df.iterrows():
        row, sheet = r["row_num"], r["source_sheet"]

        # --- Subtotal rows pasted into the sheet (e.g. 'QUARTER 1 TOTAL') would double-count ---
        if "TOTAL" in (clean_text(r["ResourceTitle"]) or "").upper():
            log_error(src, row, "ResourceTitle", f"{r['ResourceTitle']} = {r['DownloadCount']}",
                      "SUBTOTAL_ROW", "REJECTED", "Manual subtotal row, not a real download record")
            continue

        # --- Date: use the format of THIS sheet, then check the year matches the sheet ---
        d = parse_date(r["Date"], [DIGITAL_SHEET_FORMATS[sheet]])
        if d is None or str(d.year) not in sheet:
            log_error(src, row, "Date", f"{sheet}: {r['Date']}", "INVALID_DATE", "REJECTED",
                      "Date does not match the sheet's format/year")
            continue

        # --- DownloadCount: text -> whole number ('1,203' -> 1203) ---
        count = parse_number(r["DownloadCount"])
        if count is None or count < 0 or count > 5000 or count != int(count):
            log_error(src, row, "DownloadCount", r["DownloadCount"], "INVALID_NUMBER", "REJECTED",
                      "DownloadCount must be a whole number between 0 and 5000")
            continue
        raw_count = str(r["DownloadCount"])
        if not raw_count.isdigit():                       # e.g. ' 7 ', '7.0', '1,203'
            log_error(src, row, "DownloadCount", raw_count, "TEXT_NUMBER", "CORRECTED",
                      f"Number stored as text (spaces/commas/decimals) -> {int(count)}")

        # --- Duration_Minutes: missing for legacy data -> keep NULL and flag it ---
        minutes = parse_number(r["Duration_Minutes"])
        if minutes is not None and not (0 <= minutes <= 600):
            log_error(src, row, "Duration_Minutes", r["Duration_Minutes"], "INVALID_RANGE", "DEFAULTED",
                      "Reading time outside 0-600 minutes -> NULL")
            minutes = None

        # --- Faculty -> department code; missing -> Unknown ---
        dept = standardize_department(r["Faculty"])
        if dept is None:
            log_error(src, row, "Faculty", r["Faculty"], "MISSING_VALUE", "DEFAULTED",
                      "Faculty missing or unknown -> Unknown department")
            dept = "UNK"

        rtype = RESOURCE_TYPE_MAP.get((clean_text(r["ResourceType"]) or "").lower(), "Unknown")
        utype = USER_TYPE_MAP.get((clean_text(r["UserType"]) or "").lower(), "Unknown")

        clean_rows.append({
            "date": d, "department_code": dept, "user_type": utype,
            "resource_title": clean_text(r["ResourceTitle"]) or "Unknown Resource",
            "resource_type": rtype, "download_count": int(count),
            "duration_minutes": int(minutes) if minutes is not None else None,
            "duration_is_missing": minutes is None,
        })
    return pd.DataFrame(clean_rows)


def transform_room_bookings(stg, students, m):
    src = "stg_room_bookings"
    df, m["exact_duplicates"] = remove_exact_duplicates(stg, src, "BookingID")
    clean_rows = []

    for _, r in df.iterrows():
        row = r["row_num"]
        try:
            bid = int(r["BookingID"])
        except (TypeError, ValueError):
            log_error(src, row, "BookingID", r["BookingID"], "INVALID_TYPE", "REJECTED", "Not a number")
            continue

        # --- BookingDate: '2024-03-15' or '15-Mar-2024' -> date ---
        d = parse_date(r["BookingDate"], ROOM_DATE_FORMATS)
        if d is None or not (FIRST_VALID_DATE <= d <= LAST_VALID_DATE):
            log_error(src, row, "BookingDate", r["BookingDate"], "INVALID_DATE", "REJECTED",
                      "Booking date is not a valid date in 2023-2025")
            continue

        # --- DurationHours: text -> number, must be between 0 and 12 ---
        hours = parse_number(r["DurationHours"])
        if hours is None or not (0 < hours <= 12):
            log_error(src, row, "DurationHours", r["DurationHours"], "INVALID_NUMBER", "REJECTED",
                      "DurationHours must be a number between 0 and 12")
            continue

        # --- RoomNumber: 'R-101', 'Room101' -> 'R101' ---
        room = standardize_room(r["RoomNumber"])
        if room is None:
            log_error(src, row, "RoomNumber", r["RoomNumber"], "UNKNOWN_REFERENCE", "DEFAULTED",
                      "Room not recognised -> UNKNOWN room")
            room = "UNKNOWN"

        # --- TimeSlot: 'Morning', '8AM-10AM', 'AM' -> '08-10' ---
        slot = TIME_SLOT_MAP.get((clean_text(r["TimeSlot"]) or "").lower())
        if slot is None:
            log_error(src, row, "TimeSlot", r["TimeSlot"], "UNKNOWN_VALUE", "DEFAULTED",
                      "Time slot not recognised -> UNK")
            slot = "UNK"

        # --- StudentID: empty = walk-in -> 'Unknown' student record ---
        sid = clean_text(r["StudentID"])
        walk_in = sid is None
        if sid is not None and sid not in students:
            log_error(src, row, "StudentID", sid, "UNKNOWN_REFERENCE", "DEFAULTED",
                      "Student not in master data -> Unknown student")
            sid = None

        purpose = PURPOSE_MAP.get((clean_text(r["Purpose"]) or "").lower(), "Unknown")

        clean_rows.append({
            "booking_id": bid, "row_num": row, "date": d, "room": room, "slot": slot,
            "student_id": sid, "is_walk_in": walk_in, "duration_hours": hours, "purpose": purpose,
            "department_code": students[sid]["department_code"] if sid else "UNK",
        })

    clean = pd.DataFrame(clean_rows).sort_values("booking_id")

    # --- Near duplicates: after standardising, a room cannot be booked twice
    #     in the same slot on the same day -> keep the first (lowest) BookingID ---
    is_dup = clean.duplicated(subset=["room", "date", "slot"], keep="first")
    for _, r in clean[is_dup].iterrows():
        log_error(src, r["row_num"], "BookingID", r["booking_id"], "DUPLICATE_NEAR", "REJECTED",
                  f"Same room {r['room']}, date and time slot as an earlier booking")
    m["near_duplicates"] = int(is_dup.sum())
    return clean[~is_dup]


# =====================================================================
# PART 6. BUILD DIMENSIONS AND FACTS (give every row its surrogate key)
# =====================================================================
def lookup_key(keys, value):
    """Find the surrogate key of a natural key. Empty value (None/NaN) -> the 'Unknown' key."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return keys[None]
    return keys[value]


def build_warehouse(students, books, loans, digital, rooms):
    print("\n[3/5] BUILD - dimensions and facts with surrogate keys")
    dw = {}

    # ---- dim_student: key 1 = Unknown, then one row per student ----
    student_keys = {None: 1}
    rows = []
    for i, sid in enumerate(sorted(students), start=2):
        s = students[sid]
        student_keys[sid] = i
        rows.append({"student_key": i, "student_id": sid, "student_id_masked": mask_student_id(sid),
                     "student_level": s["student_level"], "year_of_study": s["year_of_study"],
                     "gender": s["gender"], "home_department_code": s["department_code"],
                     "valid_from": "2000-01-01", "valid_to": "9999-12-31", "is_current": True})
    dw["dim_student"] = pd.DataFrame(rows)

    # ---- dim_book: key 1 = Unknown Book ----
    book_keys = {None: 1}
    rows = []
    for i, isbn in enumerate(sorted(books), start=2):
        book_keys[isbn] = i
        rows.append({"book_key": i, **books[isbn]})
    dw["dim_book"] = pd.DataFrame(rows)

    # ---- dim_resource: one row per (title, type) found in the digital data ----
    resource_keys = {}
    rows = []
    unique_res = digital[["resource_title", "resource_type"]].drop_duplicates().sort_values(
        ["resource_type", "resource_title"])
    for i, (title, rtype) in enumerate(unique_res.itertuples(index=False), start=2):
        resource_keys[(title, rtype)] = i
        rows.append({"resource_key": i, "resource_title": title, "resource_type": rtype})
    dw["dim_resource"] = pd.DataFrame(rows)

    # ---- fact_book_loan ----
    dw["fact_book_loan"] = pd.DataFrame({
        "loan_key": range(1, len(loans) + 1),
        "transaction_id": loans["transaction_id"].values,
        "checkout_date_key": [date_key(d) for d in loans["checkout_date"]],
        "return_date_key": [date_key(d) for d in loans["return_date"]],
        "student_key": [lookup_key(student_keys, s) for s in loans["student_id"]],
        "department_key": [DEPARTMENT_KEYS[d] for d in loans["department_code"]],
        "book_key": [lookup_key(book_keys, b) for b in loans["isbn"]],
        "loan_count": 1,
        "loan_duration_days": loans["loan_duration_days"].values,
        "is_returned": loans["is_returned"].values,
        "is_overdue": loans["is_overdue"].values,
        "etl_batch_id": BATCH_ID,
    })

    # ---- fact_digital_usage ----
    dw["fact_digital_usage"] = pd.DataFrame({
        "usage_key": range(1, len(digital) + 1),
        "date_key": [date_key(d) for d in digital["date"]],
        "department_key": [DEPARTMENT_KEYS[d] for d in digital["department_code"]],
        "user_type_key": [USER_TYPE_KEYS[u] for u in digital["user_type"]],
        "resource_key": [resource_keys[(t, r)] for t, r in zip(digital["resource_title"], digital["resource_type"])],
        "download_count": digital["download_count"].values,
        "duration_minutes": digital["duration_minutes"].values,
        "duration_is_missing": digital["duration_is_missing"].values,
        "etl_batch_id": BATCH_ID,
    })

    # ---- fact_room_booking ----
    dw["fact_room_booking"] = pd.DataFrame({
        "booking_key": range(1, len(rooms) + 1),
        "booking_id": rooms["booking_id"].values,
        "date_key": [date_key(d) for d in rooms["date"]],
        "time_slot_key": [TIME_SLOT_KEYS[s] for s in rooms["slot"]],
        "room_key": [ROOM_KEYS[r] for r in rooms["room"]],
        "student_key": [lookup_key(student_keys, s) for s in rooms["student_id"]],
        "department_key": [DEPARTMENT_KEYS[d] for d in rooms["department_code"]],
        "purpose_key": [PURPOSE_KEYS[p] for p in rooms["purpose"]],
        "booking_count": 1,
        "duration_hours": rooms["duration_hours"].values,
        "is_walk_in": rooms["is_walk_in"].values,
        "etl_batch_id": BATCH_ID,
    })

    for name, df in dw.items():
        print(f"      {name:24s} {len(df):>6} rows")
    return dw


# =====================================================================
# PART 7. VALIDATE before loading (stop the load if a check fails)
# =====================================================================
def validate(dw):
    print("\n[4/5] VALIDATE - checks before loading")
    loans, dig, rooms = dw["fact_book_loan"], dw["fact_digital_usage"], dw["fact_room_booking"]
    first_key, last_key = date_key(FIRST_VALID_DATE), date_key(LAST_VALID_DATE)
    checks = [
        ("No duplicate TransactionID in fact_book_loan", loans["transaction_id"].is_unique),
        ("No duplicate BookingID in fact_room_booking", rooms["booking_id"].is_unique),
        ("No room double-booked in the same slot",
         not rooms.duplicated(["room_key", "date_key", "time_slot_key"]).any()),
        ("All checkout dates inside 2023-2025", loans["checkout_date_key"].between(first_key, last_key).all()),
        ("All download dates inside 2023-2025", dig["date_key"].between(first_key, last_key).all()),
        ("All booking dates inside 2023-2025", rooms["date_key"].between(first_key, last_key).all()),
        ("Loan durations are never negative", (loans["loan_duration_days"].dropna() >= 0).all()),
        ("Download counts are never negative", (dig["download_count"] >= 0).all()),
        ("Booking hours between 0 and 12", rooms["duration_hours"].between(0.5, 12).all()),
        ("Every student_key exists in dim_student",
         set(loans["student_key"]) | set(rooms["student_key"]) <= set(dw["dim_student"]["student_key"]) | {1}),
        ("Every book_key exists in dim_book", set(loans["book_key"]) <= set(dw["dim_book"]["book_key"]) | {1}),
        ("No NULL department_key in any fact",
         not (loans["department_key"].isna().any() or dig["department_key"].isna().any()
              or rooms["department_key"].isna().any())),
    ]
    results = []
    for name, passed in checks:
        print(f"      [{'PASS' if passed else 'FAIL'}] {name}")
        results.append({"check": name, "result": "PASS" if passed else "FAIL"})
    if not all(passed for _, passed in checks):
        raise RuntimeError("Validation failed - nothing was loaded. See the messages above.")
    return results


# =====================================================================
# PART 8. LOAD - write sample_data.sql and run it in the SQLite database
# =====================================================================
def sql_value(v):
    """Turn a Python value into SQL text: None -> NULL, True -> 1, 'O'Brien' -> 'O''Brien'."""
    if v is None:
        return "NULL"
    if isinstance(v, (bool, np.bool_)):
        return "1" if v else "0"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        if pd.isna(v):
            return "NULL"
        return str(int(v)) if float(v).is_integer() else str(float(v))   # 5.0 -> 5
    if v is pd.NA:
        return "NULL"
    if isinstance(v, (date, datetime)):
        return f"'{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


def insert_statements(table, df, columns, sql_columns=None, chunk=500):
    """Create INSERT statements, 500 rows per statement (much faster than 1 row at a time).
    columns     = the DataFrame columns to take the values from
    sql_columns = the column names to write in SQL (if different, e.g. "Date")"""
    sql_columns = sql_columns or columns
    statements = []
    for start in range(0, len(df), chunk):
        part = df.iloc[start:start + chunk]
        values = ",\n".join("(" + ", ".join(sql_value(v) for v in row) + ")"
                            for row in part[columns].itertuples(index=False))
        statements.append(f"INSERT INTO {table} ({', '.join(sql_columns)}) VALUES\n{values};")
    return statements


def build_sql(staging, dw, metrics_total):
    """All statements of the load, in the order they must run, inside ONE transaction:
    if any statement fails, SQLite undoes everything (nothing half-loaded)."""
    s = ["BEGIN TRANSACTION;"]

    # ---------- 1. batch log: mark this batch as RUNNING ----------
    #      (while a batch is RUNNING the audit triggers stay quiet)
    s.append(
        "INSERT OR REPLACE INTO etl_batch_log (batch_id, load_type, started_at, status, notes) VALUES "
        f"({BATCH_ID}, '{LOAD_TYPE}', '{metrics_total['started_at']}', 'RUNNING', "
        "'Full load of 3 sources + 2 reference files');")

    # ---------- 2. staging area: empty it and store the raw rows ----------
    for t in ["stg_book_transactions", "stg_digital_usage", "stg_room_bookings",
              "stg_student_master", "stg_book_catalog"]:
        s.append(f"DELETE FROM {t};")
    s.append(f"DELETE FROM etl_error_log WHERE batch_id = {BATCH_ID};")
    staging_columns = {
        "stg_book_transactions": ["TransactionID", "StudentID", "BookISBN", "CheckoutDate", "ReturnDate",
                                  "Department", "BookCategory"],
        "stg_digital_usage": ["Date", "UserType", "ResourceType", "ResourceTitle", "Faculty",
                              "DownloadCount", "Duration_Minutes", "source_sheet"],
        "stg_room_bookings": ["BookingID", "RoomNumber", "BookingDate", "TimeSlot", "StudentID",
                              "DurationHours", "Purpose"],
        "stg_student_master": ["StudentID", "Department", "StudentLevel", "YearOfStudy", "Gender"],
        "stg_book_catalog": ["BookISBN", "Title", "Author", "Publisher", "PublicationYear", "BookCategory"],
    }
    for table, cols in staging_columns.items():
        df = staging[table].copy()
        df["batch_id"] = BATCH_ID
        cols = cols + ["batch_id", "source_file"]
        if table in ("stg_book_transactions", "stg_digital_usage", "stg_room_bookings"):
            cols.append("row_num")                       # only the 3 sources store the line number
        sql_cols = ['"Date"' if c == "Date" else c for c in cols]   # "Date" in quotes: it is also a function name
        s.extend(insert_statements(table, df, cols, sql_cols))
    if error_log:
        s.extend(insert_statements("etl_error_log", pd.DataFrame(error_log),
                                   ["batch_id", "source_table", "source_row_num", "column_name", "bad_value",
                                    "error_type", "action_taken", "message"]))

    # ---------- 3. warehouse: facts first (they point to the dimensions) ----------
    for t in ["fact_book_loan", "fact_digital_usage", "fact_room_booking"]:
        s.append(f"DELETE FROM {t};")
    s.append("DELETE FROM dim_student  WHERE student_key  > 1;")    # keep the 'Unknown' rows (key 1)
    s.append("DELETE FROM dim_book     WHERE book_key     > 1;")
    s.append("DELETE FROM dim_resource WHERE resource_key > 1;")
    for name in ["dim_student", "dim_book", "dim_resource",          # dimensions before facts
                 "fact_book_loan", "fact_digital_usage", "fact_room_booking"]:
        df = dw[name]
        s.extend(insert_statements(name, df, list(df.columns)))

    # ---------- 4. batch log: SUCCESS + counts ----------
    s.append(
        f"UPDATE etl_batch_log SET status = 'SUCCESS', finished_at = '{metrics_total['finished_at']}', "
        f"rows_extracted = {metrics_total['rows_extracted']}, rows_loaded = {metrics_total['rows_loaded']}, "
        f"rows_rejected = {metrics_total['rows_rejected']} WHERE batch_id = {BATCH_ID};")
    s.append("COMMIT;")
    return s


def write_sql_file(statements):
    header = (
        "-- =====================================================================\n"
        "-- sample_data.sql  -  GENERATED by 04_ETL_Files/etl_script.py\n"
        f"-- Created: {datetime.now():%Y-%m-%d %H:%M}   Batch: {BATCH_ID}   Load type: {LOAD_TYPE}\n"
        "-- SQLite. Run AFTER scripts 01-07 (or: python build_database.py --with-data).\n"
        "-- It fills the staging area (raw data + error log) and the warehouse\n"
        "-- (dimensions + facts) inside ONE transaction. Safe to run again: it\n"
        "-- empties the tables first, so no duplicates are created.\n"
        "-- =====================================================================\n\n")
    with open(SQL_FILE, "w", encoding="utf-8") as f:
        f.write(header + "\n\n".join(statements) + "\n")
    print(f"      wrote {os.path.relpath(SQL_FILE, PROJECT)}  ({os.path.getsize(SQL_FILE) // 1024} KB)")


def open_database():
    """Open library_dw.db. If it does not exist yet, build it with scripts 01-07 first."""
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys = ON")          # SQLite: must be switched on per connection
    has_tables = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name = 'fact_book_loan'").fetchone()[0]
    if not has_tables:
        con.close()
        print("      database not found -> building it with scripts 01-07")
        sys.path.insert(0, DB_DIR)
        import build_database                         # 03_Database_Files/build_database.py
        build_database.build(with_data=False, db_file=DB_FILE)
        con = sqlite3.connect(DB_FILE)
        con.execute("PRAGMA foreign_keys = ON")
    return con


def load_cleansing_rules(con):
    """Read the mapping tables from the database and check the fixed dimension keys."""
    DEPARTMENT_MAP.update(dict(con.execute("SELECT lower(raw_value), department_code FROM map_department")))
    TIME_SLOT_MAP.update(dict(con.execute("SELECT lower(raw_value), slot_code FROM map_time_slot")))
    # the surrogate keys used in this script must be the ones in the database
    for table, code_col, key_col, keys in [
            ("dim_department", "department_code", "department_key", DEPARTMENT_KEYS),
            ("dim_time_slot", "slot_code", "time_slot_key", TIME_SLOT_KEYS),
            ("dim_room", "room_number", "room_key", ROOM_KEYS),
            ("dim_user_type", "user_type", "user_type_key", USER_TYPE_KEYS),
            ("dim_booking_purpose", "purpose_name", "purpose_key", PURPOSE_KEYS)]:
        in_db = dict(con.execute(f"SELECT {code_col}, {key_col} FROM {table}"))
        if in_db != keys:
            raise RuntimeError(f"{table} in the database does not match the keys in etl_script.py")
    print(f"      cleansing rules from database: {len(DEPARTMENT_MAP)} department spellings, "
          f"{len(TIME_SLOT_MAP)} time-slot spellings")


def load_into_sqlite(con, dw):
    """Run sample_data.sql in the database (one transaction), then check the result."""
    with open(SQL_FILE, encoding="utf-8") as f:
        script = f.read()
    try:
        con.executescript(script)
    except sqlite3.Error:
        con.rollback()                                # undo the whole batch
        con.execute("UPDATE etl_batch_log SET status = 'FAILED' WHERE batch_id = ?", (BATCH_ID,))
        con.commit()
        raise
    # Post-load checks: the database must contain exactly what we prepared
    for name in ["dim_student", "dim_book", "dim_resource", "fact_book_loan",
                 "fact_digital_usage", "fact_room_booking"]:
        in_db = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        expected = len(dw[name]) + (1 if name.startswith("dim_") else 0)      # + the 'Unknown' row
        if in_db != expected:
            raise RuntimeError(f"{name}: {in_db} rows in database, {expected} expected")
    problems = con.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(f"{len(problems)} foreign key problems after loading")
    print(f"      loaded into {os.path.relpath(DB_FILE, PROJECT)}: row counts match, 0 foreign key problems")


def export_csv(dw):
    """Write clean tables as CSV for Power BI. dim_student WITHOUT the real StudentID (privacy)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("dimdate", os.path.join(HERE, "reference_dimensions.py"))
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    tables = dict(dw)
    # the 'Unknown' rows (key 1) live in the database already; add them to the CSV files too
    unknown = ref.unknown_rows()
    for name in ("dim_student", "dim_book", "dim_resource"):
        tables[name] = pd.concat([pd.DataFrame([unknown[name]]), dw[name]], ignore_index=True)
    tables["dim_student"] = tables["dim_student"].drop(columns=["student_id"])
    tables.update(ref.reference_tables())                   # date, department, room, time slot ...
    for name, df in tables.items():
        df.to_csv(os.path.join(CSV_DIR, f"{name}.csv"), index=False)
    print(f"      wrote {len(tables)} clean CSV files -> 06_Dashboards/PowerBI_Data/")


# =====================================================================
# PART 9. DATA QUALITY METRICS (before vs after) + readable error log
# =====================================================================
def profile(series):
    """Number of different spellings in a column (ignoring empty values)."""
    return int(series.dropna().astype(str).str.strip().replace("", None).dropna().nunique())


def quality_metrics(staging, loans, digital, rooms, per_source):
    b, d, r = staging["stg_book_transactions"], staging["stg_digital_usage"], staging["stg_room_bookings"]
    missing = lambda s: int(s.isna().sum())
    return {
        "book_transactions": {
            "rows_before": len(b), "rows_after": len(loans), **per_source["book"],
            "department_spellings": [profile(b["Department"]), int(loans["department_code"].nunique())],
            "date_formats": [int(b["CheckoutDate"].map(date_pattern).nunique()), 1],
            "isbn_formats": [int(b["BookISBN"].str.contains("-").nunique()), 1],
            "category_spellings": [profile(b["BookCategory"]), 4],
            "missing_department": [missing(b["Department"]), 0],
            "missing_return_date": [missing(b["ReturnDate"]), int((~loans["is_returned"]).sum())],
        },
        "digital_usage": {
            "rows_before": len(d), "rows_after": len(digital), **per_source["digital"],
            "faculty_spellings": [profile(d["Faculty"]), int(digital["department_code"].nunique())],
            "date_formats": [int(d["Date"].map(date_pattern).nunique()), 1],
            "resource_type_spellings": [profile(d["ResourceType"]), int(digital["resource_type"].nunique())],
            "user_type_spellings": [profile(d["UserType"]), int(digital["user_type"].nunique())],
            "download_count_as_text": [int(d["DownloadCount"].astype(str).str.contains(r"[^0-9]").sum()), 0],
            "missing_duration": [missing(d["Duration_Minutes"]), int(digital["duration_is_missing"].sum())],
            "missing_faculty": [missing(d["Faculty"]), 0],
        },
        "room_bookings": {
            "rows_before": len(r), "rows_after": len(rooms), **per_source["room"],
            "room_spellings": [profile(r["RoomNumber"]), int(rooms["room"].nunique())],
            "time_slot_spellings": [profile(r["TimeSlot"]), int(rooms["slot"].nunique())],
            "date_formats": [int(r["BookingDate"].map(date_pattern).nunique()), 1],
            "duration_as_text": [int(r["DurationHours"].astype(str).str.contains(r"[a-zA-Z]").sum()), 0],
            "purpose_spellings": [profile(r["Purpose"]), int(rooms["purpose"].nunique())],
            "missing_student_id": [missing(r["StudentID"]), 0],
            "walk_ins_mapped_to_unknown": int(rooms["is_walk_in"].sum()),
        },
    }


def write_error_log_files():
    log = pd.DataFrame(error_log)
    log.to_csv(os.path.join(OUTPUT_DIR, "etl_error_log.csv"), index=False)

    lines = [
        "=" * 100,
        f" ETL ERROR LOG (SAMPLE) - University Library DW - batch {BATCH_ID} - {datetime.now():%Y-%m-%d %H:%M}",
        f" Full log: output/etl_error_log.csv and table library_staging.etl_error_log ({len(log)} entries)",
        "=" * 100, "", "SUMMARY BY SOURCE, ERROR TYPE AND ACTION", "-" * 60,
    ]
    summary = log.groupby(["source_table", "error_type", "action_taken"]).size()
    for (src, etype, action), n in summary.items():
        lines.append(f" {src:24s} {etype:20s} {action:10s} {n:>5}")
    lines += ["", "HOW EACH ACTION IS HANDLED", "-" * 60,
              " REJECTED  : row is NOT loaded into the warehouse (kept in staging for review)",
              " CORRECTED : value fixed automatically (e.g. department filled from master data)",
              " DEFAULTED : value replaced with 'Unknown' / NULL so the row can still be used",
              "", "SAMPLE ENTRIES (first 5 of each error type)", "-" * 100,
              f" {'ID':>5} | {'source':22s} | {'row':>5} | {'column':16s} | {'bad value':28s} | "
              f"{'error type':18s} | {'action':9s} | message", "-" * 100]
    for _, grp in log.groupby("error_type"):
        for _, e in grp.head(5).iterrows():
            lines.append(f" {e.error_id:>5} | {e.source_table:22s} | {e.source_row_num:>5} | "
                         f"{e.column_name:16s} | {str(e.bad_value)[:28]:28s} | {e.error_type:18s} | "
                         f"{e.action_taken:9s} | {e.message}")
    with open(os.path.join(HERE, "error_log_sample.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"      wrote error_log_sample.txt and output/etl_error_log.csv ({len(log)} entries)")


# =====================================================================
# MAIN - run all steps in order
# =====================================================================
def main():
    global BATCH_ID
    started = datetime.now()
    con = open_database()
    BATCH_ID = con.execute("SELECT COALESCE(MAX(batch_id), 0) + 1 FROM etl_batch_log").fetchone()[0]
    print("=" * 62)
    print(f" LIBRARY DATA WAREHOUSE - ETL batch {BATCH_ID} ({LOAD_TYPE} load, SQLite)")
    print("=" * 62)
    load_cleansing_rules(con)

    staging = extract()

    print("\n[2/5] TRANSFORM - cleaning and standardising")
    students = transform_students(staging["stg_student_master"])
    books = transform_books(staging["stg_book_catalog"])
    per_source = {"book": {}, "digital": {}, "room": {}}
    loans = transform_book_transactions(staging["stg_book_transactions"], students, books, per_source["book"])
    digital = transform_digital_usage(staging["stg_digital_usage"], per_source["digital"])
    rooms = transform_room_bookings(staging["stg_room_bookings"], students, per_source["room"])
    print(f"      book loans {len(loans)}, digital rows {len(digital)}, room bookings {len(rooms)}")
    print(f"      problems logged: {len(error_log)}")

    dw = build_warehouse(students, books, loans, digital, rooms)
    checks = validate(dw)

    print("\n[5/5] LOAD - SQL file, SQLite database, CSV files and reports")
    sources = ["stg_book_transactions", "stg_digital_usage", "stg_room_bookings"]
    extracted = sum(len(staging[t]) for t in sources)
    loaded = len(loans) + len(digital) + len(rooms)
    totals = {"started_at": f"{started:%Y-%m-%d %H:%M:%S}", "finished_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
              "rows_extracted": extracted, "rows_loaded": loaded, "rows_rejected": extracted - loaded}
    statements = build_sql(staging, dw, totals)
    write_sql_file(statements)
    load_into_sqlite(con, dw)
    con.close()
    export_csv(dw)
    write_error_log_files()

    metrics = {"batch": totals, "validation": checks,
               "sources": quality_metrics(staging, loans, digital, rooms, per_source)}
    with open(os.path.join(OUTPUT_DIR, "quality_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print(f"\nETL finished in {(datetime.now() - started).total_seconds():.1f} s: "
          f"{extracted} rows read, {loaded} loaded, {extracted - loaded} rejected (see error log).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # ERROR HANDLING: if anything fails, nothing half-finished is loaded.
        # The message is saved so the team can see what went wrong.
        with open(os.path.join(OUTPUT_DIR, "etl_failure.log"), "a") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  batch {BATCH_ID}  FAILED: {exc!r}\n")
        print(f"\nETL FAILED: {exc}\nDetails saved in output/etl_failure.log")
        raise
