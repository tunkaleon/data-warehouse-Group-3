"""
reference_dimensions.py
-----------------------------------------------------------------------
The small "fixed" dimensions (date, department, user type, room, time
slot, booking purpose) are created INSIDE the SQLite database by
03_create_dimension_tables.sql.

Power BI can also read the warehouse from CSV files (easier than
installing an ODBC driver), so etl_script.py uses this file to write the
SAME rows to CSV. The values here must match script 03 (the ETL checks it).
-----------------------------------------------------------------------
"""

from datetime import date, timedelta
import pandas as pd


def make_dim_date(first=date(2023, 1, 1), last=date(2027, 12, 31)):
    """One row per day - the same columns as dim_date in the database."""
    rows = []
    d = first
    while d <= last:
        month = d.month
        rows.append({
            "date_key": int(d.strftime("%Y%m%d")),
            "full_date": d.isoformat(),
            "day_of_month": d.day,
            "day_name": d.strftime("%A"),
            "day_of_week": d.isoweekday(),                 # 1 = Monday ... 7 = Sunday
            "is_weekend": int(d.isoweekday() >= 6),
            "week_of_year": int(d.strftime("%W")),         # weeks start on Monday (same as SQLite)
            "week_start_date": (d - timedelta(days=d.weekday())).isoformat(),
            "month_num": month,
            "month_name": d.strftime("%B"),
            "month_short": d.strftime("%b"),
            "month_label": d.strftime("%Y-%m"),
            "quarter_num": (month - 1) // 3 + 1,
            "quarter_name": f"Q{(month - 1) // 3 + 1}",
            "year_num": d.year,
            "academic_year": f"{d.year}/{d.year + 1}" if month >= 9 else f"{d.year - 1}/{d.year}",
            "semester": "Semester 1" if month in (9, 10, 11, 12, 1)
                        else "Semester 2" if month in (2, 3, 4, 5, 6) else "Break",
        })
        d += timedelta(days=1)
    # special row used when a book is not returned yet
    rows.insert(0, {"date_key": -1, "full_date": "1900-01-01", "day_of_month": 0, "day_name": "N/A",
                    "day_of_week": 0, "is_weekend": 0, "week_of_year": 0,
                    "week_start_date": "1900-01-01", "month_num": 0, "month_name": "N/A",
                    "month_short": "N/A", "month_label": "N/A", "quarter_num": 0, "quarter_name": "NA",
                    "year_num": 0, "academic_year": "N/A", "semester": "N/A"})
    return pd.DataFrame(rows)


def reference_tables():
    """Return all fixed dimensions as DataFrames (same rows as the seed data of script 03)."""
    department = pd.DataFrame([
        (1, "UNK", "Unknown", "Unknown"),
        (2, "CS", "Computer Science", "Faculty of Computing & IT"),
        (3, "ENG", "Engineering", "Faculty of Engineering & Technology"),
        (4, "BUS", "Business", "Faculty of Business & Economics"),
        (5, "MED", "Health Sciences", "Faculty of Medicine & Health Sciences"),
        (6, "EDU", "Education", "Faculty of Education"),
        (7, "LAW", "Law", "Faculty of Law"),
        (8, "ART", "Arts & Humanities", "Faculty of Arts & Social Sciences"),
        (9, "SCI", "Natural Sciences", "Faculty of Science"),
    ], columns=["department_key", "department_code", "department_name", "faculty_name"])

    user_type = pd.DataFrame([
        (1, "Unknown", "Unknown", "Unknown"),
        (2, "Undergraduate Student", "Student", "Undergraduate"),
        (3, "Graduate Student", "Student", "Graduate"),
        (4, "Faculty", "Employee", "N/A"),
        (5, "Staff", "Employee", "N/A"),
    ], columns=["user_type_key", "user_type", "user_group", "student_level"])

    room = pd.DataFrame([
        (1, "UNKNOWN", 0, 0, "Unknown", 0, 0, 0),
        (2, "R101", 1, 4, "Group", 0, 1, 0),
        (3, "R102", 1, 6, "Group", 1, 1, 0),
        (4, "R103", 1, 2, "Individual", 0, 0, 1),
        (5, "R104", 1, 2, "Individual", 0, 0, 1),
        (6, "R201", 2, 8, "Group", 1, 1, 0),
        (7, "R202", 2, 4, "Group", 0, 1, 0),
        (8, "R203", 2, 1, "Individual", 0, 0, 1),
        (9, "R204", 2, 12, "Seminar", 1, 1, 0),
        (10, "R301", 3, 6, "Group", 1, 1, 0),
        (11, "R302", 3, 20, "Seminar", 1, 1, 0),
        (12, "R303", 3, 1, "Individual", 0, 0, 1),
    ], columns=["room_key", "room_number", "floor_num", "capacity", "room_type",
                "has_projector", "has_whiteboard", "is_quiet_zone"])

    time_slot = pd.DataFrame([
        (1, "UNK", "Unknown", 0, 0, "Unknown"),
        (2, "08-10", "08:00 - 10:00", 8, 10, "Morning"),
        (3, "10-12", "10:00 - 12:00", 10, 12, "Morning"),
        (4, "12-14", "12:00 - 14:00", 12, 14, "Afternoon"),
        (5, "14-16", "14:00 - 16:00", 14, 16, "Afternoon"),
        (6, "16-18", "16:00 - 18:00", 16, 18, "Afternoon"),
        (7, "18-20", "18:00 - 20:00", 18, 20, "Evening"),
    ], columns=["time_slot_key", "slot_code", "slot_label", "start_hour", "end_hour", "day_period"])

    purpose = pd.DataFrame([
        (1, "Unknown", "Unknown"), (2, "Study", "Individual"), (3, "Exam Preparation", "Individual"),
        (4, "Research", "Individual"), (5, "Group Project", "Collaborative"),
        (6, "Meeting", "Collaborative"), (7, "Tutorial", "Collaborative"),
    ], columns=["purpose_key", "purpose_name", "purpose_group"])

    return {"dim_date": make_dim_date(), "dim_department": department, "dim_user_type": user_type,
            "dim_room": room, "dim_time_slot": time_slot, "dim_booking_purpose": purpose}


def unknown_rows():
    """The 'Unknown' member (key 1) of the dimensions that the ETL fills."""
    return {
        "dim_student": {"student_key": 1, "student_id": "UNKNOWN", "student_id_masked": "UNKNOWN",
                        "student_level": "Unknown", "year_of_study": None, "gender": None,
                        "home_department_code": "UNK", "valid_from": "2000-01-01",
                        "valid_to": "9999-12-31", "is_current": 1},
        "dim_book": {"book_key": 1, "isbn": "UNKNOWN", "title": "Unknown Book", "author": None,
                     "publisher": None, "publication_year": None, "book_category": "Unknown"},
        "dim_resource": {"resource_key": 1, "resource_title": "Unknown Resource", "resource_type": "Unknown"},
    }
