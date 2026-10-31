"""
=====================================================================
 dashboard_data.py  -  the SQL behind the three web dashboards
=====================================================================
 Every function receives a logged-in secure_access Session and runs its
 SQL through session.con. That connection has the SQLite AUTHORIZER of
 the user's role switched on, so the database itself enforces security:

   executive_data()    director     (dw_analyst)  -> dim_ / fact_ tables
   department_data()   head_cs ...  (dw_dept_head)-> ONLY the private my_*
                                                      tables of HIS department
   operational_data()  ops_manager  (dw_analyst)  -> dim_ / fact_ tables

 Each function returns a Python dict. app.py sends it to the web page as
 JSON and the page draws the charts (static/charts.js).
=====================================================================
"""

from datetime import date, timedelta


def rows(session, sql, params=()):
    """Run one SELECT and return the rows as a list of dicts (column -> value)."""
    cur = session.con.execute(sql, params)
    names = [c[0] for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def one(session, sql, params=()):
    """Run a SELECT that returns ONE value (e.g. a SUM)."""
    value = session.con.execute(sql, params).fetchone()[0]
    return value if value is not None else 0


def change(now, before):
    """Percentage change from last year (None when there is no last year)."""
    return round(100.0 * (now - before) / before, 1) if before else None


# =====================================================================
# 1. EXECUTIVE DASHBOARD  (library director)
# =====================================================================
def year_kpis(session, year):
    """The six headline numbers for one year."""
    loans = one(session, """SELECT SUM(f.loan_count) FROM fact_book_loan f
                            JOIN dim_date d ON d.date_key = f.checkout_date_key WHERE d.year_num = ?""", (year,))
    downloads = one(session, """SELECT SUM(f.download_count) FROM fact_digital_usage f
                                JOIN dim_date d ON d.date_key = f.date_key WHERE d.year_num = ?""", (year,))
    bookings = one(session, """SELECT SUM(f.booking_count) FROM fact_room_booking f
                               JOIN dim_date d ON d.date_key = f.date_key WHERE d.year_num = ?""", (year,))
    returned = rows(session, """SELECT AVG(f.loan_duration_days) AS avg_days,
                                       100.0 * SUM(f.is_overdue) / COUNT(*) AS overdue_pct
                                FROM fact_book_loan f JOIN dim_date d ON d.date_key = f.checkout_date_key
                                WHERE d.year_num = ? AND f.is_returned = 1""", (year,))[0]
    return {"loans": loans, "downloads": downloads, "bookings": bookings,
            "avg_days": round(returned["avg_days"] or 0, 1),
            "overdue_pct": round(returned["overdue_pct"] or 0, 1),
            "per_loan": round(downloads / loans, 1) if loans else 0}


def available_years(session):
    """Years that really contain data (the date dimension goes up to 2027)."""
    return [r["year_num"] for r in rows(session, """
        SELECT DISTINCT d.year_num FROM fact_book_loan f
        JOIN dim_date d ON d.date_key = f.checkout_date_key ORDER BY 1""")]


def executive_data(session, year):
    now = year_kpis(session, year)
    before = year_kpis(session, year - 1)
    kpis = [
        {"label": "Book loans",          "value": f"{now['loans']:,}",
         "change": change(now["loans"], before["loans"]), "good_when": "up"},
        {"label": "Digital downloads",   "value": f"{now['downloads']:,}",
         "change": change(now["downloads"], before["downloads"]), "good_when": "up"},
        {"label": "Room bookings",       "value": f"{now['bookings']:,}",
         "change": change(now["bookings"], before["bookings"]), "good_when": "up"},
        {"label": "Avg loan duration",   "value": f"{now['avg_days']} days",
         "change": change(now["avg_days"], before["avg_days"]), "good_when": "down"},
        {"label": "Overdue loans (>21 days)", "value": f"{now['overdue_pct']}%",
         "change": change(now["overdue_pct"], before["overdue_pct"]), "good_when": "down"},
        {"label": "Downloads per book loan", "value": f"{now['per_loan']}",
         "change": change(now["per_loan"], before["per_loan"]), "good_when": "up"},
    ]

    # Usage index per month: 100 = an average month of 2023 (shows digital replacing books)
    monthly = rows(session, """
        SELECT d.month_label AS month,
               (SELECT IFNULL(SUM(loan_count), 0) FROM fact_book_loan f
                  JOIN dim_date x ON x.date_key = f.checkout_date_key WHERE x.month_label = d.month_label) AS loans,
               (SELECT IFNULL(SUM(download_count), 0) FROM fact_digital_usage f
                  JOIN dim_date x ON x.date_key = f.date_key WHERE x.month_label = d.month_label) AS downloads,
               (SELECT IFNULL(SUM(booking_count), 0) FROM fact_room_booking f
                  JOIN dim_date x ON x.date_key = f.date_key WHERE x.month_label = d.month_label) AS bookings
        FROM dim_date d WHERE d.year_num BETWEEN 2023 AND 2025
        GROUP BY d.month_label ORDER BY d.month_label""")
    base = {k: sum(m[k] for m in monthly if m["month"].startswith("2023")) / 12 for k in ("loans", "downloads", "bookings")}
    trend = {"labels": [m["month"] for m in monthly],
             "series": [{"name": "Digital downloads", "values": [round(100 * m["downloads"] / base["downloads"]) for m in monthly]},
                        {"name": "Room bookings",     "values": [round(100 * m["bookings"] / base["bookings"]) for m in monthly]},
                        {"name": "Book loans",        "values": [round(100 * m["loans"] / base["loans"]) for m in monthly]}]}

    resource_mix = rows(session, """
        SELECT r.resource_type AS label, SUM(f.download_count) AS value
        FROM fact_digital_usage f JOIN dim_resource r ON r.resource_key = f.resource_key
        JOIN dim_date d ON d.date_key = f.date_key
        WHERE d.year_num = ? AND r.resource_type <> 'Unknown'
        GROUP BY r.resource_type ORDER BY value DESC""", (year,))

    departments = rows(session, """
        SELECT dp.department_name AS label, SUM(u.n) AS value
        FROM (SELECT f.department_key, f.loan_count AS n, d.year_num FROM fact_book_loan f
                JOIN dim_date d ON d.date_key = f.checkout_date_key
              UNION ALL
              SELECT f.department_key, f.download_count, d.year_num FROM fact_digital_usage f
                JOIN dim_date d ON d.date_key = f.date_key
              UNION ALL
              SELECT f.department_key, f.booking_count, d.year_num FROM fact_room_booking f
                JOIN dim_date d ON d.date_key = f.date_key) u
        JOIN dim_department dp ON dp.department_key = u.department_key
        WHERE u.year_num = ? AND dp.department_code <> 'UNK'
        GROUP BY dp.department_name ORDER BY value DESC""", (year,))

    top_books = rows(session, """
        SELECT b.title, b.book_category AS category, SUM(f.loan_count) AS loans
        FROM fact_book_loan f JOIN dim_book b ON b.book_key = f.book_key
        JOIN dim_date d ON d.date_key = f.checkout_date_key
        WHERE d.year_num = ? AND b.book_key <> 1
        GROUP BY b.title, b.book_category ORDER BY loans DESC LIMIT 5""", (year,))

    return {"year": year, "years": available_years(session), "kpis": kpis, "trend": trend,
            "resource_mix": resource_mix, "departments": departments, "top_books": top_books,
            "alerts": download_anomalies(session)}


def download_anomalies(session):
    """Same method as query Q13 in 05_Analytics_Package/business_queries.sql:
       1. seasonal index = downloads of the month / average month of THAT year (removes yearly growth)
       2. normal index   = average index of the same calendar month in the OTHER years
       3. ANOMALY when the index is below 50% of normal (a sudden drop)."""
    data = rows(session, """
        SELECT d.year_num AS y, d.month_num AS m, d.month_name AS name, SUM(f.download_count) AS n
        FROM fact_digital_usage f JOIN dim_date d ON d.date_key = f.date_key
        GROUP BY d.year_num, d.month_num""")
    for r in data:
        year_months = [o["n"] for o in data if o["y"] == r["y"]]
        r["index"] = r["n"] / (sum(year_months) / len(year_months))
    alerts = []
    for r in data:
        others = [o["index"] for o in data if o["m"] == r["m"] and o["y"] != r["y"]]
        normal = sum(others) / len(others) if others else 0
        if normal and r["index"] < 0.5 * normal:
            alerts.append(f"{r['name']} {r['y']}: digital downloads {round(100 * (r['index'] - normal) / normal)}% "
                          f"vs a normal {r['name']} (e-resource platform outage?)")
    return alerts


# =====================================================================
# 2. DEPARTMENT DASHBOARD  (department head - row-level security)
#    Only the private TEMP tables my_book_loans, my_digital_usage,
#    my_room_bookings and my_monthly_summary can be read. They were
#    filled at login with the rows of THIS head's department only.
# =====================================================================
def department_data(session, year):
    where_loan = "WHERE checkout_date LIKE ?" if year else ""
    where_dl = "WHERE download_date LIKE ?" if year else ""
    where_room = "WHERE booking_date LIKE ?" if year else ""
    where_month = "WHERE month_label LIKE ?" if year else ""
    p = (f"{year}-%",) if year else ()

    loans = rows(session, f"""
        SELECT COUNT(*) AS loans,
               AVG(CASE WHEN is_returned = 1 THEN loan_duration_days END) AS avg_days,
               100.0 * SUM(CASE WHEN is_returned = 1 THEN is_overdue ELSE 0 END)
                     / NULLIF(SUM(is_returned), 0) AS overdue_pct,
               SUM(CASE WHEN is_returned = 0 THEN 1 ELSE 0 END) AS still_out
        FROM my_book_loans {where_loan}""", p)[0]
    downloads = one(session, f"SELECT SUM(download_count) FROM my_digital_usage {where_dl}", p)
    journals = one(session, f"SELECT SUM(download_count) FROM my_digital_usage "
                            f"{where_dl + ' AND' if year else 'WHERE'} resource_type = 'Journal'", p)
    # COUNT(column), not COUNT(*): the authorizer must see a real column of my_room_bookings
    bookings = one(session, f"SELECT COUNT(booking_date) FROM my_room_bookings {where_room}", p)

    kpis = [
        {"label": "Book loans", "value": f"{loans['loans']:,}"},
        {"label": "Digital downloads", "value": f"{downloads:,}"},
        {"label": "Room bookings", "value": f"{bookings:,}"},
        {"label": "Avg loan duration", "value": f"{round(loans['avg_days'] or 0, 1)} days"},
        {"label": "Overdue loans", "value": f"{round(loans['overdue_pct'] or 0, 1)}%"},
        {"label": "Journal share of downloads", "value": f"{round(100 * journals / downloads, 1) if downloads else 0}%"},
    ]

    monthly = rows(session, f"SELECT month_label AS month, book_loans, digital_downloads, room_bookings "
                            f"FROM my_monthly_summary {where_month} ORDER BY month_label", p)
    trend = {"labels": [m["month"] for m in monthly],
             "series": [{"name": "Digital downloads", "values": [m["digital_downloads"] for m in monthly]},
                        {"name": "Room bookings", "values": [m["room_bookings"] for m in monthly]},
                        {"name": "Book loans", "values": [m["book_loans"] for m in monthly]}]}

    resource_mix = rows(session, f"""SELECT resource_type AS label, SUM(download_count) AS value
                                     FROM my_digital_usage {where_dl} GROUP BY resource_type ORDER BY value DESC""", p)
    levels = rows(session, f"""
        SELECT student_level AS label, ROUND(AVG(loan_duration_days), 1) AS value
        FROM my_book_loans {where_loan + ' AND' if year else 'WHERE'} is_returned = 1
             AND student_level IN ('Undergraduate', 'Graduate')
        GROUP BY student_level ORDER BY student_level DESC""", p)
    purposes = rows(session, f"""SELECT purpose_name AS label, COUNT(*) AS value FROM my_room_bookings {where_room}
                                 GROUP BY purpose_name ORDER BY value DESC""", p)
    top_books = rows(session, f"""SELECT title, book_category AS category, COUNT(*) AS loans
                                  FROM my_book_loans {where_loan} GROUP BY title, book_category
                                  ORDER BY loans DESC LIMIT 5""", p)
    # recent loans: the student column is MASKED (STU-****-001) - the head never sees the real ID
    recent = rows(session, f"""SELECT checkout_date, student, student_level, title,
                                      CASE WHEN is_returned = 1 THEN 'Returned' ELSE 'Out' END AS status
                               FROM my_book_loans {where_loan} ORDER BY checkout_date DESC LIMIT 8""", p)
    years = [r["y"] for r in rows(session, "SELECT DISTINCT substr(month_label, 1, 4) AS y "
                                           "FROM my_monthly_summary ORDER BY 1")]
    return {"year": year, "years": years, "kpis": kpis, "trend": trend, "resource_mix": resource_mix,
            "levels": levels, "purposes": purposes, "top_books": top_books, "recent": recent}


# =====================================================================
# 3. OPERATIONAL DASHBOARD  (operations manager - daily running of the library)
# =====================================================================
OPEN_HOURS_PER_DAY = 12          # 08:00-20:00 = 6 time slots of 2 hours


def operational_data(session):
    last_day = date.fromisoformat(one(session, """SELECT MAX(d.full_date) FROM fact_room_booking f
                                                  JOIN dim_date d ON d.date_key = f.date_key"""))
    d30 = (last_day - timedelta(days=29)).isoformat()            # last 30 days
    d60 = (last_day - timedelta(days=59)).isoformat()            # previous 30 days start
    rooms = one(session, "SELECT COUNT(*) FROM dim_room WHERE room_key <> 1")

    period = rows(session, """
        SELECT SUM(f.booking_count) AS bookings, SUM(f.duration_hours) AS hours,
               SUM(f.is_walk_in) AS walk_ins
        FROM fact_room_booking f JOIN dim_date d ON d.date_key = f.date_key
        WHERE d.full_date BETWEEN ? AND ?""", (d30, last_day.isoformat()))[0]
    prev_hours = one(session, """SELECT SUM(f.duration_hours) FROM fact_room_booking f
                                 JOIN dim_date d ON d.date_key = f.date_key
                                 WHERE d.full_date >= ? AND d.full_date < ?""", (d60, d30))
    out_now = one(session, "SELECT COUNT(*) FROM fact_book_loan WHERE is_returned = 0")
    out_30 = one(session, """SELECT COUNT(*) FROM fact_book_loan f JOIN dim_date d ON d.date_key = f.checkout_date_key
                             WHERE f.is_returned = 0 AND d.full_date < ?""", (d30,))
    bookings, hours = period["bookings"] or 0, period["hours"] or 0
    kpis = [
        {"label": "Room bookings", "value": f"{bookings}", "note": "last 30 days"},
        {"label": "Hours booked", "value": f"{hours:.0f} h", "note": f"previous 30 days: {prev_hours:.0f} h"},
        {"label": "Room utilisation", "value": f"{100 * hours / (30 * OPEN_HOURS_PER_DAY * rooms):.1f}%",
         "note": "booked hours / open hours"},
        {"label": "Walk-in bookings", "value": f"{round(100 * (period['walk_ins'] or 0) / bookings) if bookings else 0}%",
         "note": "no StudentID recorded"},
        {"label": "Books currently out", "value": f"{out_now}", "note": "not yet returned"},
        {"label": "Out longer than 30 days", "value": f"{out_30}", "note": "follow up at the desk"},
    ]

    # heat map: bookings per weekday x time slot in the last year
    heat_rows = rows(session, """
        SELECT d.day_of_week AS dow, substr(d.day_name, 1, 3) AS day, t.slot_label AS slot,
               SUM(f.booking_count) AS n
        FROM fact_room_booking f JOIN dim_date d ON d.date_key = f.date_key
        JOIN dim_time_slot t ON t.time_slot_key = f.time_slot_key
        WHERE d.year_num = ? AND t.time_slot_key <> 1
        GROUP BY d.day_of_week, t.slot_label ORDER BY d.day_of_week, t.slot_label""", (last_day.year,))
    days = list(dict.fromkeys(r["day"] for r in heat_rows))
    slots = sorted(set(r["slot"] for r in heat_rows))
    grid = [[next((r["n"] for r in heat_rows if r["day"] == dname and r["slot"] == s), 0) for s in slots] for dname in days]
    busiest = max(heat_rows, key=lambda r: r["n"])

    # daily bookings for the last 60 days + 7-day moving average
    daily = {r["day"]: r["n"] for r in rows(session, """
        SELECT d.full_date AS day, SUM(f.booking_count) AS n FROM fact_room_booking f
        JOIN dim_date d ON d.date_key = f.date_key WHERE d.full_date >= ? GROUP BY d.full_date""", (d60,))}
    days60 = [(last_day - timedelta(days=i)).isoformat() for i in range(59, -1, -1)]
    counts = [daily.get(dd, 0) for dd in days60]
    avg7 = [round(sum(counts[max(0, i - 6): i + 1]) / len(counts[max(0, i - 6): i + 1]), 1) for i in range(len(counts))]

    utilisation = rows(session, """
        SELECT r.room_number || '  ' || r.room_type || ', ' || r.capacity || ' seats' AS label,
               ROUND(100.0 * SUM(f.duration_hours) / (365 * ?), 1) AS value
        FROM fact_room_booking f JOIN dim_room r ON r.room_key = f.room_key
        JOIN dim_date d ON d.date_key = f.date_key
        WHERE d.year_num = ? AND r.room_key <> 1
        GROUP BY r.room_number ORDER BY value DESC""", (OPEN_HOURS_PER_DAY, last_day.year))

    ages = rows(session, """
        SELECT CASE WHEN julianday(?) - julianday(d.full_date) <= 14 THEN '0-14 d'
                    WHEN julianday(?) - julianday(d.full_date) <= 30 THEN '15-30 d'
                    WHEN julianday(?) - julianday(d.full_date) <= 90 THEN '31-90 d'
                    ELSE '90+ d' END AS label, COUNT(*) AS value
        FROM fact_book_loan f JOIN dim_date d ON d.date_key = f.checkout_date_key
        WHERE f.is_returned = 0 GROUP BY label ORDER BY MIN(julianday(?) - julianday(d.full_date))""",
                (last_day.isoformat(),) * 4)

    alerts = [{"level": "red", "title": "Anomaly - digital downloads", "text": a} for a in download_anomalies(session)]
    alerts.append({"level": "orange", "title": "Busiest slot",
                   "text": f"{busiest['day']} {busiest['slot']} ({busiest['n']} bookings in {last_day.year}) - "
                           f"open an overflow room or add staff at the desk"})
    duplicates = one(session, "SELECT COUNT(*) - COUNT(DISTINCT transaction_id) FROM fact_book_loan")
    alerts.append({"level": "green" if duplicates == 0 else "red", "title": "Data quality",
                   "text": f"{duplicates} duplicate loans in the warehouse"})

    return {"last_day": last_day.isoformat(), "kpis": kpis,
            "heat": {"days": days, "slots": slots, "grid": grid},
            "daily": {"labels": days60, "bookings": counts, "avg7": avg7},
            "utilisation": utilisation, "ages": ages, "alerts": alerts}
