"""
=====================================================================
 generate_source_data.py
 University Library Analytics - SAMPLE SOURCE DATA GENERATOR
=====================================================================
 WHY THIS SCRIPT EXISTS
 The assignment does not give us real library data, so this script
 SIMULATES the three legacy systems and creates their export files:

   1. book_transactions.csv  -> Book Lending System (MySQL export)
   2. digital_usage.xlsx     -> Digital Resources System (Excel, 3 sheets)
   3. room_bookings.csv      -> Study Room Booking System (CSV export)
   + reference/student_master.csv  (Registrar list of students)
   + reference/book_catalog.csv    (library catalogue of books)

 IMPORTANT: the data is made DIRTY ON PURPOSE. It contains every
 problem listed in section 7 of the brief (mixed date formats,
 "CS" vs "CompSci", R-101 vs Room101, NULLs, duplicates, numbers
 stored as text ...) so that our ETL script can prove it fixes them.

 HOW TO RUN
     python generate_source_data.py
 The same "random seed" is used every time, so you always get exactly
 the same files (useful when the team compares results).
=====================================================================
"""

import random
import csv
import os
from datetime import date, timedelta

import pandas as pd   # only used to write the Excel file

# ---------------------------------------------------------------------
# 0. SETTINGS
# ---------------------------------------------------------------------
random.seed(42)                      # fixed seed = same data every run
START_DATE = date(2023, 1, 1)        # first day of data
END_DATE   = date(2025, 12, 31)      # last day of data (3 full years)

# Folder where this script lives -> files are written next to it
HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.join(HERE, "reference")
os.makedirs(REF_DIR, exist_ok=True)


# ---------------------------------------------------------------------
# 1. DEPARTMENTS and their MESSY spellings
#    The key is the clean code; the list holds the different ways the
#    old systems type the same department.
# ---------------------------------------------------------------------
DEPARTMENTS = {
    "CS":  ["CS", "Computer Science", "CompSci", "Comp Sci", "computer science"],
    "ENG": ["ENG", "Engineering", "Engr", "Eng.", "engineering "],
    "BUS": ["BUS", "Business", "Business Admin", "Bus. Admin"],
    "MED": ["MED", "Medicine", "Health Sciences", "Med"],
    "EDU": ["EDU", "Education", "Educ"],
    "LAW": ["LAW", "Law", "law"],
    "ART": ["ART", "Arts", "Arts & Humanities", "Humanities"],
    "SCI": ["SCI", "Science", "Natural Sciences", "Sciences"],
}
# How big each department is (share of all students)
DEPT_WEIGHTS = {"CS": 20, "ENG": 20, "BUS": 15, "MED": 13,
                "EDU": 10, "LAW": 7, "ART": 7, "SCI": 8}


def messy_department(code):
    """Return a random spelling of a department, like a careless user would type it."""
    return random.choice(DEPARTMENTS[code])


# ---------------------------------------------------------------------
# 2. SEASONALITY - libraries are busy before exams and quiet in holidays
#    (1.0 = normal month). Used by all three systems.
# ---------------------------------------------------------------------
MONTH_FACTOR = {1: 0.90, 2: 1.00, 3: 1.10, 4: 1.30, 5: 1.10, 6: 0.80,
                7: 0.35, 8: 0.40, 9: 1.00, 10: 1.10, 11: 1.30, 12: 0.70}


def all_days():
    """List every date between START_DATE and END_DATE."""
    days = []
    d = START_DATE
    while d <= END_DATE:
        days.append(d)
        d += timedelta(days=1)
    return days


def poisson(mean):
    """Random whole number of events around 'mean' (simple Poisson draw)."""
    # Knuth's method - fine for small means like ours
    import math
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= random.random()
        if p <= limit:
            return k
        k += 1


# =====================================================================
# 3. STUDENT MASTER DATA (reference file from the Registrar)
# =====================================================================
def make_students(n=800):
    """Create n students: ID, department, level, year of study, gender."""
    students = []
    counter = {}                                    # running number per intake year
    codes = list(DEPT_WEIGHTS.keys())
    weights = list(DEPT_WEIGHTS.values())
    for _ in range(n):
        intake = random.choice([2019, 2020, 2021, 2022, 2023, 2024, 2025])
        counter[intake] = counter.get(intake, 0) + 1
        student_id = f"STU-{intake}-{counter[intake]:03d}"   # e.g. STU-2024-001
        level = "Graduate" if random.random() < 0.20 else "Undergraduate"
        students.append({
            "StudentID": student_id,
            "Department": random.choices(codes, weights)[0],
            "StudentLevel": level,
            "YearOfStudy": random.randint(1, 2) if level == "Graduate" else random.randint(1, 4),
            "Gender": random.choice(["M", "F"]),
            # hidden helper (NOT written to file): some students use the library a lot
            "_activity": random.lognormvariate(0, 0.8),
        })
    return students


# =====================================================================
# 4. BOOK CATALOGUE (reference file)
# =====================================================================
SUBJECT_TITLES = {
    "CS":  ["Programming Fundamentals with Python", "Data Structures and Algorithms",
            "Database Systems Design", "Computer Networks Explained", "Operating Systems Principles",
            "Introduction to Machine Learning", "Software Engineering in Practice", "Data Mining and Warehousing"],
    "ENG": ["Engineering Mathematics", "Fluid Mechanics Basics", "Electrical Circuit Analysis",
            "Strength of Materials", "Thermodynamics for Engineers", "Civil Engineering Drawing"],
    "BUS": ["Principles of Accounting", "Introduction to Microeconomics", "Marketing Management",
            "Business Statistics", "Entrepreneurship in Africa", "Financial Management"],
    "MED": ["Human Anatomy Atlas", "Clinical Pharmacology", "Principles of Public Health",
            "Medical Physiology", "Community Nursing Care"],
    "EDU": ["Educational Psychology", "Curriculum Development", "Classroom Assessment Methods",
            "Inclusive Education"],
    "LAW": ["Constitutional Law", "Law of Contract", "Criminal Procedure", "International Human Rights Law"],
    "ART": ["World History Survey", "Introduction to Linguistics", "African Literature Anthology",
            "Philosophy and Ethics"],
    "SCI": ["General Chemistry", "University Physics", "Cell Biology", "Calculus I", "Statistics for Science"],
}
FICTION_TITLES = ["The River Between Hills", "Morning in Kigali", "The Last Lantern",
                  "Songs of the Rain", "A Bridge of Stones", "The Silent Market",
                  "Echoes of Lake Kivu", "The Teacher's Daughter"]
REFERENCE_TITLES = ["Oxford Style Dictionary", "Academic Writing Handbook",
                    "Research Methods Guide", "World Atlas 2022", "Encyclopedia of Science"]
FIRST = ["J.", "A.", "M.", "K.", "E.", "P.", "S.", "T.", "D.", "R."]
LAST = ["Mugisha", "Uwase", "Smith", "Okoro", "Habimana", "Mensah", "Brown", "Ingabire",
        "Kamau", "Niyonzima", "Garcia", "Mutesi", "Wilson", "Banda"]
PUBLISHERS = ["Academic Press", "Kigali University Press", "Global Learning", "Lakeside Publishing",
              "Continental Books"]


def make_isbn():
    """Create a valid-looking ISBN-13 like 978-0134685991 (with correct check digit)."""
    digits = [9, 7, 8] + [random.randint(0, 9) for _ in range(9)]
    total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    check = (10 - total % 10) % 10
    number = "".join(str(d) for d in digits) + str(check)
    return number[:3] + "-" + number[3:]


def make_books():
    """Create the book catalogue. Each book has a 'popularity' so some books are borrowed a lot."""
    books = []

    def add(title, category, dept):
        books.append({
            "BookISBN": make_isbn(),
            "Title": title,
            "Author": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "Publisher": random.choice(PUBLISHERS),
            "PublicationYear": random.randint(2008, 2023),
            "BookCategory": category,
            "_dept": dept,                                   # hidden helper
            "_popularity": random.paretovariate(1.6),        # few very popular books
        })

    for dept, titles in SUBJECT_TITLES.items():
        for t in titles:
            add(t, "Textbook", dept)
            if random.random() < 0.4:                        # some research monographs
                add(t + ": Advanced Readings", "Research", dept)
    for t in FICTION_TITLES:
        add(t, "Fiction", None)
    for t in REFERENCE_TITLES:
        add(t, "Reference", None)
    return books


# =====================================================================
# 5. SOURCE 1 - BOOK TRANSACTIONS  (book_transactions.csv)
# =====================================================================
def format_old_date(d):
    """Historical (2023) records were typed in different date formats."""
    style = random.choice(["%m/%d/%Y", "%b %d, %Y", "%Y-%m-%d"])
    return d.strftime(style)


def make_book_transactions(students, books):
    rows = []
    weights_students = [s["_activity"] for s in students]
    tid = 1001                                     # TransactionID starts at 1001 (as in the brief)

    for day in all_days():
        years_passed = (day - START_DATE).days / 365
        trend = 1.0 - 0.10 * years_passed          # physical borrowing falls ~10% per year
        weekday = 0.3 if day.weekday() >= 5 else 1.0
        expected = 3.2 * trend * MONTH_FACTOR[day.month] * weekday

        for _ in range(poisson(expected)):
            st = random.choices(students, weights_students)[0]

            # graduates often borrow research books; 60% of loans are from
            # the student's own department, the rest can be any book
            research = [b for b in books if b["BookCategory"] == "Research"]
            if st["StudentLevel"] == "Graduate" and random.random() < 0.45:
                pool = research
            elif random.random() < 0.6:
                pool = [b for b in books if b["_dept"] == st["Department"]]
            else:
                pool = books
            bk = random.choices(pool, [b["_popularity"] for b in pool])[0]

            # How long the book is kept (graduates keep books longer; reference books short)
            if bk["BookCategory"] == "Reference":
                days_kept = random.randint(1, 7)
            elif st["StudentLevel"] == "Graduate":
                days_kept = int(random.triangular(5, 35, 16))
            else:
                days_kept = int(random.triangular(2, 28, 10))
            return_day = day + timedelta(days=days_kept)

            # ---- Missing ReturnDate (book not returned yet) ----
            not_returned = return_day > END_DATE or random.random() < 0.145
            # ---- Date format: old 2023 data uses mixed formats ----
            fmt = format_old_date if day.year == 2023 else (lambda d: d.isoformat())

            # ---- ISBN: some clerks type it without the dash ----
            isbn = bk["BookISBN"] if random.random() < 0.85 else bk["BookISBN"].replace("-", "")

            # ---- Book category with inconsistent capitalisation ----
            category = bk["BookCategory"]
            if random.random() < 0.08:
                category = random.choice([category.lower(), category.upper()])

            rows.append({
                "TransactionID": tid,
                "StudentID": st["StudentID"],
                "BookISBN": isbn,
                "CheckoutDate": fmt(day),
                "ReturnDate": "" if not_returned else fmt(return_day),
                # ---- 3% of rows lost their department (system error) ----
                "Department": "" if random.random() < 0.03 else messy_department(st["Department"]),
                "BookCategory": category,
            })
            tid += 1

    # ---- PROBLEM: exact duplicates (same TransactionID appears twice) ----
    for r in random.sample(rows, k=int(len(rows) * 0.02)):
        rows.append(dict(r))
    # ---- PROBLEM: logical duplicates (same student + book + date, new ID) ----
    for r in random.sample(rows, k=int(len(rows) * 0.01)):
        dup = dict(r)
        dup["TransactionID"] = tid
        tid += 1
        rows.append(dup)
    # ---- PROBLEM: invalid / impossible values ----
    bad = random.sample(rows, k=12)
    for r in bad[:4]:
        r["CheckoutDate"] = random.choice(["2024-02-30", "13/45/2023", "2023-00-12", "N/A"])
    for r in bad[4:8]:                              # return date BEFORE checkout date
        if r["ReturnDate"]:
            r["CheckoutDate"], r["ReturnDate"] = r["ReturnDate"], r["CheckoutDate"]
    for r in bad[8:]:                               # ISBN that is not in the catalogue
        r["BookISBN"] = make_isbn()

    rows.sort(key=lambda r: r["TransactionID"])      # like a database export
    return rows


# =====================================================================
# 6. SOURCE 2 - DIGITAL USAGE  (digital_usage.xlsx, one sheet per year)
# =====================================================================
# Each year's sheet was kept by a different staff member -> 3 date formats
SHEET_DATE_FORMATS = {
    2023: "%m/%d/%Y",     # 01/15/2023  (American style)
    2024: "%Y-%d-%m",     # 2024-15-01  (year-DAY-month, a common Excel mistake)
    2025: "%b %d, %Y",    # Jan 15, 2025
}
USER_TYPES = {   # clean meaning : messy spellings found in the file
    "Undergraduate": ["Student", "student", "Undergraduate", "UG Student"],
    "Graduate":      ["Grad Student", "Graduate", "grad student", "Postgraduate"],
    "Faculty":       ["Faculty", "Lecturer", "faculty"],
    "Staff":         ["Staff", "staff"],
}
USER_WEIGHTS = {"Undergraduate": 55, "Graduate": 25, "Faculty": 15, "Staff": 5}
RESOURCE_SPELLINGS = {
    "E-book":  ["E-book", "e-Book", "ebook", "E-Book", "EBOOK"],
    "Journal": ["Journal", "journal", "JOURNAL"],
    "Article": ["Article", "article", "Article "],
}
JOURNALS = ["Journal of Applied Computing", "African Journal of Engineering Research",
            "International Journal of Data Science", "Journal of Business Studies",
            "East African Medical Journal", "Journal of Education Practice",
            "Law and Society Review", "Journal of Renewable Energy", "Journal of Public Health Africa",
            "Information Systems Quarterly", "Journal of Environmental Science",
            "Computational Linguistics Today", "Review of Development Economics", "Nursing Research Digest"]
EBOOKS = [t + " (e-book)" for titles in SUBJECT_TITLES.values() for t in titles[:3]]
ARTICLES = ["Cloud Computing Adoption in Rwanda", "Solar Mini-Grids Case Study", "Mobile Money and SMEs",
            "Malaria Prevention Strategies", "Remote Learning After 2020", "Big Data in Agriculture",
            "Water Quality Monitoring", "Women in STEM Education"]


def make_resources():
    """Every digital resource has a title, a type and a popularity weight."""
    res = []
    for title_list, rtype in [(JOURNALS, "Journal"), (EBOOKS, "E-book"), (ARTICLES, "Article")]:
        for t in title_list:
            res.append({"title": t, "type": rtype, "_pop": random.paretovariate(1.4)})
    return res


def datetime_from(text, year):
    """Read back a date written with the format of the given year's sheet."""
    from datetime import datetime
    return datetime.strptime(text, SHEET_DATE_FORMATS[year])


def make_digital_usage():
    resources = make_resources()
    rows_by_year = {2023: [], 2024: [], 2025: []}

    for day in all_days():
        years_passed = (day - START_DATE).days / 365
        trend = 1.0 + 0.30 * years_passed               # digital use GROWS ~30% per year
        weekday = 0.6 if day.weekday() >= 5 else 1.0    # people download at weekends too
        expected = 3.2 * trend * MONTH_FACTOR[day.month] * weekday

        # ---- ANOMALY: e-resource platform outage 7-27 Oct 2024 ----
        if date(2024, 10, 7) <= day <= date(2024, 10, 27):
            expected *= 0.15

        for _ in range(poisson(expected)):
            user = random.choices(list(USER_WEIGHTS), list(USER_WEIGHTS.values()))[0]
            # graduates & faculty prefer journals, undergraduates prefer e-books
            if user in ("Graduate", "Faculty"):
                type_weights = {"Journal": 50, "E-book": 25, "Article": 25}
            else:
                type_weights = {"Journal": 20, "E-book": 60, "Article": 20}
            rtype = random.choices(list(type_weights), list(type_weights.values()))[0]
            pool = [r for r in resources if r["type"] == rtype]
            res = random.choices(pool, [r["_pop"] for r in pool])[0]
            dept = random.choices(list(DEPT_WEIGHTS), list(DEPT_WEIGHTS.values()))[0]

            count = max(1, int(random.lognormvariate(1.4, 0.7)))   # mostly 1-12 downloads
            minutes = int(random.triangular(5, 180, 40))

            # ---- PROBLEM: DownloadCount stored as TEXT instead of a number ----
            count_value = count
            r = random.random()
            if r < 0.006:
                count_value = f" {count} "                          # extra spaces
            elif r < 0.012:
                count_value = f"{count}.0"                          # decimal text
            elif r < 0.015:
                count_value = random.choice(["N/A", "-3", "two"])   # invalid -> must be rejected

            # ---- PROBLEM: Duration_Minutes missing for legacy (2023) records ----
            if day.year == 2023 and random.random() < 0.70:
                minutes = None
            elif random.random() < 0.05:
                minutes = None

            rows_by_year[day.year].append({
                "Date": day.strftime(SHEET_DATE_FORMATS[day.year]),
                "UserType": random.choice(USER_TYPES[user]),
                "ResourceType": random.choice(RESOURCE_SPELLINGS[rtype]),
                "ResourceTitle": res["title"],
                # ---- PROBLEM: faculty codes vary; 2% missing ----
                "Faculty": "" if random.random() < 0.02 else messy_department(dept),
                "DownloadCount": count_value,
                "Duration_Minutes": minutes,
            })

    # ---- PROBLEM: staff pasted QUARTER TOTAL rows into the sheets.
    #      Their numbers have thousands commas ("1,203") and they would
    #      double-count downloads if loaded. ----
    for year, rows in rows_by_year.items():
        for q in range(1, 5):
            months = range(3 * q - 2, 3 * q + 1)
            in_quarter = [x for x in rows if isinstance(x["DownloadCount"], int)
                          and datetime_from(x["Date"], year).month in months]
            total = sum(x["DownloadCount"] for x in in_quarter)
            last_day = date(year, 3 * q, 31 if q in (1, 4) else 30)
            rows.append({"Date": last_day.strftime(SHEET_DATE_FORMATS[year]), "UserType": "",
                         "ResourceType": "", "ResourceTitle": f"QUARTER {q} TOTAL", "Faculty": "",
                         "DownloadCount": f"{total:,}", "Duration_Minutes": None})

    # ---- PROBLEM: some rows were copied twice in Excel ----
    for year, rows in rows_by_year.items():
        for r in random.sample(rows, k=int(len(rows) * 0.015)):
            rows.append(dict(r))
        random.shuffle(rows)
    return rows_by_year


# =====================================================================
# 7. SOURCE 3 - ROOM BOOKINGS  (room_bookings.csv)
# =====================================================================
ROOMS = {   # room : (popularity weight)  -> group rooms with projector are favourites
    "R101": 8, "R102": 12, "R103": 5, "R104": 5, "R201": 14, "R202": 8,
    "R203": 4, "R204": 6, "R301": 12, "R302": 3, "R303": 4,
}
# clean slot code : messy ways the web app stored it
SLOT_SPELLINGS = {
    "08-10": ["8AM-10AM", "08:00-10:00", "Morning", "AM"],
    "10-12": ["10AM-12PM", "10:00-12:00", "Late Morning"],
    "12-14": ["12PM-2PM", "12:00-14:00", "Midday", "Noon"],
    "14-16": ["2PM-4PM", "14:00-16:00", "Afternoon", "PM"],
    "16-18": ["4PM-6PM", "16:00-18:00", "Late Afternoon"],
    "18-20": ["6PM-8PM", "18:00-20:00", "Evening"],
}
SLOT_WEIGHTS = {"08-10": 10, "10-12": 18, "12-14": 14, "14-16": 26, "16-18": 20, "18-20": 12}
WEEKDAY_FACTOR = [1.0, 1.2, 1.25, 1.15, 0.85, 0.35, 0.2]   # Mon ... Sun
PURPOSES = {"Study": 30, "Group Project": 28, "Exam Preparation": 15, "Meeting": 12,
            "Research": 8, "Tutorial": 7}
PURPOSE_SPELLINGS = {"Group Project": ["Group Project", "group project", "Group project"],
                     "Exam Preparation": ["Exam Preparation", "Exam Prep", "exam prep"]}


def messy_room(room):
    """R101 -> one of R101, R-101, Room101, Room 101, r101"""
    num = room[1:]
    return random.choice([room, f"R-{num}", f"Room{num}", f"Room {num}", f"r{num}"])


def messy_hours(h):
    """2.0 -> '2.0', '2', '2 hrs' or '2.0h' (text, as exported by the web app)"""
    return random.choice([f"{h:.1f}", f"{h:g}", f"{h:g} hrs", f"{h:.1f}h"])


def make_room_bookings(students):
    rows = []
    bid = 5001                                       # BookingID starts at 5001 (as in the brief)
    room_list, room_w = list(ROOMS), list(ROOMS.values())
    stu_w = [s["_activity"] for s in students]

    for day in all_days():
        years_passed = (day - START_DATE).days / 365
        expected = 3.0 * (1 + 0.08 * years_passed) * MONTH_FACTOR[day.month] * WEEKDAY_FACTOR[day.weekday()]
        taken = set()                                # a room can only be booked once per slot
        for _ in range(poisson(expected)):
            room = random.choices(room_list, room_w)[0]
            slot = random.choices(list(SLOT_WEIGHTS), list(SLOT_WEIGHTS.values()))[0]
            if (room, slot) in taken:
                continue
            taken.add((room, slot))

            walk_in = random.random() < 0.08          # ---- 8% walk-ins: no StudentID ----
            student = "" if walk_in else random.choices(students, stu_w)[0]["StudentID"]
            hours = random.choice([1.0, 1.5, 2.0, 2.0, 2.0, 2.5, 3.0, 3.5, 4.0])
            purpose = random.choices(list(PURPOSES), list(PURPOSES.values()))[0]
            purpose_text = random.choice(PURPOSE_SPELLINGS.get(purpose, [purpose]))

            # ---- Date format: two styles ----
            date_text = day.isoformat() if random.random() < 0.6 else day.strftime("%d-%b-%Y")

            rows.append({
                "BookingID": bid,
                "RoomNumber": messy_room(room),
                "BookingDate": date_text,
                "TimeSlot": random.choice(SLOT_SPELLINGS[slot]),
                "StudentID": student,
                "DurationHours": messy_hours(hours),
                "Purpose": purpose_text,
            })
            bid += 1

    # ---- PROBLEM: exact duplicates (system error, same BookingID twice) ----
    for r in random.sample(rows, k=int(len(rows) * 0.04)):
        rows.append(dict(r))
    # ---- PROBLEM: near duplicates (same booking saved again with a new ID,
    #      the time slot written differently and a slightly different duration) ----
    for r in random.sample(rows, k=int(len(rows) * 0.015)):
        dup = dict(r)
        dup["BookingID"] = bid
        bid += 1
        clean_slot = next(k for k, v in SLOT_SPELLINGS.items() if r["TimeSlot"] in v)
        dup["TimeSlot"] = random.choice(SLOT_SPELLINGS[clean_slot])
        dup["RoomNumber"] = messy_room("R" + "".join(c for c in r["RoomNumber"] if c.isdigit()))
        rows.append(dup)
    # ---- PROBLEM: invalid values ----
    bad = random.sample(rows, k=10)
    for r in bad[:3]:
        r["BookingDate"] = random.choice(["31-Feb-2024", "2024-13-01", ""])
    for r in bad[3:7]:
        r["DurationHours"] = random.choice(["", "abc", "15", "-2"])
    for r in bad[7:]:
        r["StudentID"] = "STU-2024-999"            # student not in the master list

    random.shuffle(rows)                             # CSV exports are not sorted
    return rows


# =====================================================================
# 8. WRITE ALL FILES
# =====================================================================
def write_csv(path, rows, columns):
    """Write a list of dictionaries to a CSV file, keeping only the given columns."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {len(rows):>5} rows -> {os.path.relpath(path, HERE)}")


def main():
    print("Generating sample source data ...")
    students = make_students()
    books = make_books()

    # Reference files (clean - they come from well-managed systems)
    write_csv(os.path.join(REF_DIR, "student_master.csv"), students,
              ["StudentID", "Department", "StudentLevel", "YearOfStudy", "Gender"])
    write_csv(os.path.join(REF_DIR, "book_catalog.csv"), books,
              ["BookISBN", "Title", "Author", "Publisher", "PublicationYear", "BookCategory"])

    # Source 1: Book Lending System
    write_csv(os.path.join(HERE, "book_transactions.csv"), make_book_transactions(students, books),
              ["TransactionID", "StudentID", "BookISBN", "CheckoutDate", "ReturnDate",
               "Department", "BookCategory"])

    # Source 2: Digital Resources System -> Excel with one sheet per year
    digital = make_digital_usage()
    xlsx_path = os.path.join(HERE, "digital_usage.xlsx")
    with pd.ExcelWriter(xlsx_path) as writer:
        for year, rows in digital.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=f"Usage_{year}", index=False)
            print(f"  wrote {len(rows):>5} rows -> digital_usage.xlsx [sheet Usage_{year}]")

    # Source 3: Study Room Booking System
    write_csv(os.path.join(HERE, "room_bookings.csv"), make_room_bookings(students),
              ["BookingID", "RoomNumber", "BookingDate", "TimeSlot", "StudentID",
               "DurationHours", "Purpose"])
    print("Done.")


if __name__ == "__main__":
    main()
