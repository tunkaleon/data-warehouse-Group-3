-- =====================================================================
--  business_queries.sql  -  University Library Analytics
--  Target: SQLite 3.35+  (file 03_Database_Files/library_dw.db, loaded by the ETL)
-- ---------------------------------------------------------------------
--  HOW TO READ THIS FILE
--  Every query starts with a header:
--     QUERY Qxx  : number + name (Q1-Q10 required, Q11-Q13 bonus, Q14+ extra)
--     Question   : the business question it answers
--     Technique  : the SQL / OLAP technique used
--     Read it as : how to interpret the result
--  HOW TO RUN
--   * DB Browser for SQLite: open library_dw.db -> "Execute SQL" tab ->
--     paste ONE query -> Ctrl+Return (results appear below)
--   * or: python run_business_queries.py  (runs ALL queries and saves
--     the results in query_results.xlsx)
--
--  SQL techniques used: aggregation (SUM, COUNT, AVG, MIN, MAX),
--  joins between fact and dimension tables, CTEs (WITH ...), window
--  functions (RANK, LAG, AVG OVER), CASE pivots, UNION ALL roll-up.
-- =====================================================================

-- =====================================================================
-- 0. THE OLAP CUBE VIEW
-- ---------------------------------------------------------------------
-- Our three services are stored in three fact tables (galaxy schema).
-- This view stacks them into ONE "cube" with the shared dimensions
-- date + department, and a "service" column. One row = usage events.
--   Book Loans        : 1 per checkout
--   Digital Downloads : number of downloads
--   Room Bookings     : 1 per booking
-- Many queries below (and the Power BI model) use this view.
-- (It is also created by 04_create_fact_tables.sql; repeating it here
--  keeps this file runnable on its own.)
-- =====================================================================
DROP VIEW IF EXISTS v_usage_cube;
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


-- =====================================================================
--                    LEVEL 1 - BASIC REPORTING
-- =====================================================================

-- ---------------------------------------------------------------------
-- QUERY Q01: Monthly usage trends (books vs digital vs rooms)
-- Question  : How does each service change month after month?
-- Technique : CTE + pivot with CASE + LAG() window function for the
--             month-over-month (MoM) % change
-- Read it as: one row per month; *_mom_pct = growth vs previous month
-- ---------------------------------------------------------------------
WITH monthly AS (
    SELECT d.month_label,
           SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
           SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
           SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings
    FROM v_usage_cube u
    JOIN dim_date d ON d.date_key = u.date_key
    GROUP BY d.month_label
)
SELECT month_label,
       book_loans,
       ROUND(100.0 * (book_loans - LAG(book_loans) OVER w)
             / NULLIF(LAG(book_loans) OVER w, 0), 1)               AS loans_mom_pct,
       digital_downloads,
       ROUND(100.0 * (digital_downloads - LAG(digital_downloads) OVER w)
             / NULLIF(LAG(digital_downloads) OVER w, 0), 1)        AS downloads_mom_pct,
       room_bookings,
       ROUND(100.0 * (room_bookings - LAG(room_bookings) OVER w)
             / NULLIF(LAG(room_bookings) OVER w, 0), 1)            AS bookings_mom_pct
FROM monthly
WINDOW w AS (ORDER BY month_label)
ORDER BY month_label;


-- ---------------------------------------------------------------------
-- QUERY Q02: Department analysis - rank departments by total usage
-- Question  : Which departments use the library most?
-- Technique : aggregation per department + RANK() + share of total
--             (SUM(...) OVER () = grand total of all departments)
-- Read it as: rank 1 = heaviest user; per-service ranks show that a
--             department can lead in one service but not in another
-- ---------------------------------------------------------------------
SELECT dp.department_name,
       SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
       SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
       SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings,
       SUM(u.usage_count)                                                  AS total_usage,
       RANK() OVER (ORDER BY SUM(u.usage_count) DESC)                      AS usage_rank,
       RANK() OVER (ORDER BY SUM(CASE WHEN u.service = 'Book Loans'
                                      THEN u.usage_count ELSE 0 END) DESC)  AS loans_rank,
       ROUND(100.0 * SUM(u.usage_count) / SUM(SUM(u.usage_count)) OVER (), 1) AS share_pct
FROM v_usage_cube u
JOIN dim_department dp ON dp.department_key = u.department_key
WHERE dp.department_code <> 'UNK'
GROUP BY dp.department_name
ORDER BY usage_rank;


-- ---------------------------------------------------------------------
-- QUERY Q03a: Peak times - heat map of room bookings (day x time slot)
-- Question  : What are the busiest hours/days for study rooms?
-- Technique : pivot (one column per time slot) with SUM(CASE ...)
-- Read it as: the biggest numbers are the peak times (= heat map
--             colours in the Operational dashboard)
-- ---------------------------------------------------------------------
SELECT d.day_name,
       SUM(CASE WHEN t.slot_code = '08-10' THEN 1 ELSE 0 END) AS "08-10",
       SUM(CASE WHEN t.slot_code = '10-12' THEN 1 ELSE 0 END) AS "10-12",
       SUM(CASE WHEN t.slot_code = '12-14' THEN 1 ELSE 0 END) AS "12-14",
       SUM(CASE WHEN t.slot_code = '14-16' THEN 1 ELSE 0 END) AS "14-16",
       SUM(CASE WHEN t.slot_code = '16-18' THEN 1 ELSE 0 END) AS "16-18",
       SUM(CASE WHEN t.slot_code = '18-20' THEN 1 ELSE 0 END) AS "18-20",
       COUNT(*)                                               AS total_bookings
FROM fact_room_booking f
JOIN dim_date d      ON d.date_key = f.date_key
JOIN dim_time_slot t ON t.time_slot_key = f.time_slot_key
GROUP BY d.day_of_week, d.day_name
ORDER BY d.day_of_week;


-- ---------------------------------------------------------------------
-- QUERY Q03b: Peak times - the 5 busiest day + time slot combinations
-- Technique : GROUP BY two dimensions + RANK()
-- ---------------------------------------------------------------------
SELECT *
FROM (
    SELECT d.day_name,
           t.slot_label,
           COUNT(*)                              AS bookings,
           ROUND(SUM(f.duration_hours), 1)       AS hours_booked,
           RANK() OVER (ORDER BY COUNT(*) DESC)  AS busy_rank
    FROM fact_room_booking f
    JOIN dim_date d      ON d.date_key = f.date_key
    JOIN dim_time_slot t ON t.time_slot_key = f.time_slot_key
    GROUP BY d.day_name, t.slot_label
) ranked
WHERE busy_rank <= 5
ORDER BY busy_rank;


-- ---------------------------------------------------------------------
-- QUERY Q04a: Popular resources - top 10 borrowed books
-- Question  : Which physical books are borrowed the most?
-- Technique : COUNT + COUNT(DISTINCT) + ORDER BY ... LIMIT 10
-- Read it as: different_students shows if a book is popular with many
--             people or borrowed again and again by a few
-- ---------------------------------------------------------------------
SELECT b.title,
       b.book_category,
       COUNT(*)                       AS times_borrowed,
       COUNT(DISTINCT f.student_key)  AS different_students,
       ROUND(AVG(f.loan_duration_days), 1) AS avg_days_kept
FROM fact_book_loan f
JOIN dim_book b ON b.book_key = f.book_key
WHERE b.book_key <> 1                            -- leave out 'Unknown Book'
GROUP BY b.book_key, b.title, b.book_category
ORDER BY times_borrowed DESC, b.title
LIMIT 10;


-- ---------------------------------------------------------------------
-- QUERY Q04b: Popular resources - top 10 downloaded journals
-- Technique : SUM of a measure, filtered on a dimension attribute
-- ---------------------------------------------------------------------
SELECT r.resource_title          AS journal,
       SUM(f.download_count)     AS total_downloads,
       COUNT(DISTINCT f.department_key) AS departments_using_it
FROM fact_digital_usage f
JOIN dim_resource r ON r.resource_key = f.resource_key
WHERE r.resource_type = 'Journal'
GROUP BY r.resource_title
ORDER BY total_downloads DESC
LIMIT 10;


-- ---------------------------------------------------------------------
-- QUERY Q05a: Efficiency - average loan duration by department and book category
-- Question  : How long are books kept? Which department/category is slowest?
-- Technique : AVG, MIN, MAX, % overdue, only RETURNED loans
-- Read it as: overdue_pct = share of loans kept longer than the 21-day loan period
-- ---------------------------------------------------------------------
SELECT dp.department_name,
       b.book_category,
       COUNT(*)                                        AS returned_loans,
       ROUND(AVG(f.loan_duration_days), 1)             AS avg_days,
       MIN(f.loan_duration_days)                       AS min_days,
       MAX(f.loan_duration_days)                       AS max_days,
       ROUND(100.0 * SUM(f.is_overdue) / COUNT(*), 1)  AS overdue_pct
FROM fact_book_loan f
JOIN dim_department dp ON dp.department_key = f.department_key
JOIN dim_book b        ON b.book_key = f.book_key
WHERE f.is_returned = 1
  AND b.book_key <> 1
GROUP BY dp.department_name, b.book_category
ORDER BY dp.department_name, b.book_category;


-- ---------------------------------------------------------------------
-- QUERY Q05b: Efficiency - average loan duration per department (summary)
-- ---------------------------------------------------------------------
SELECT dp.department_name,
       COUNT(*)                                        AS returned_loans,
       ROUND(AVG(f.loan_duration_days), 1)             AS avg_days,
       ROUND(100.0 * SUM(f.is_overdue) / COUNT(*), 1)  AS overdue_pct
FROM fact_book_loan f
JOIN dim_department dp ON dp.department_key = f.department_key
WHERE f.is_returned = 1
GROUP BY dp.department_name
ORDER BY avg_days DESC;


-- =====================================================================
--                    LEVEL 2 - OLAP OPERATIONS
-- =====================================================================

-- ---------------------------------------------------------------------
-- QUERY Q06a: DRILL-DOWN level 1 - YEAR
-- Question  : Start with yearly usage, then go down to quarter,
--             month and day (Q06a -> Q06b -> Q06c -> Q06d)
-- Technique : the SAME measure grouped by a more detailed level of the
--             date hierarchy each time (Year > Quarter > Month > Day)
-- Note      : a library has no revenue, so "usage" is our measure.
-- ---------------------------------------------------------------------
SELECT d.year_num,
       SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
       SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
       SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings
FROM v_usage_cube u
JOIN dim_date d ON d.date_key = u.date_key
GROUP BY d.year_num
ORDER BY d.year_num;

-- ---------------------------------------------------------------------
-- QUERY Q06b: DRILL-DOWN level 2 - QUARTERS of 2024
-- ---------------------------------------------------------------------
SELECT d.year_num, d.quarter_name,
       SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
       SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
       SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings
FROM v_usage_cube u
JOIN dim_date d ON d.date_key = u.date_key
WHERE d.year_num = 2024
GROUP BY d.year_num, d.quarter_name
ORDER BY d.quarter_name;

-- ---------------------------------------------------------------------
-- QUERY Q06c: DRILL-DOWN level 3 - MONTHS of Q2 2024 (exam season)
-- ---------------------------------------------------------------------
SELECT d.month_label, d.month_name,
       SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
       SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
       SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings
FROM v_usage_cube u
JOIN dim_date d ON d.date_key = u.date_key
WHERE d.year_num = 2024 AND d.quarter_num = 2
GROUP BY d.month_label, d.month_name
ORDER BY d.month_label;

-- ---------------------------------------------------------------------
-- QUERY Q06d: DRILL-DOWN level 4 - DAYS of April 2024
-- ---------------------------------------------------------------------
SELECT d.full_date, d.day_name,
       SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
       SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
       SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings
FROM v_usage_cube u
JOIN dim_date d ON d.date_key = u.date_key
WHERE d.month_label = '2024-04'
GROUP BY d.full_date, d.day_name
ORDER BY d.full_date;


-- ---------------------------------------------------------------------
-- QUERY Q07a: ROLL-UP level 1 - DAILY room bookings (Q1 2024)
-- Question  : Aggregate daily room bookings into weekly and monthly
--             summaries (Q07a -> Q07b -> Q07c, then Q07d in one query)
-- Technique : the opposite of drill-down: go UP the hierarchy
--             Day > Week > Month, adding the details together
-- ---------------------------------------------------------------------
SELECT d.full_date, d.day_name,
       COUNT(*)                         AS bookings,
       ROUND(SUM(f.duration_hours), 1)  AS hours_booked
FROM fact_room_booking f
JOIN dim_date d ON d.date_key = f.date_key
WHERE d.year_num = 2024 AND d.quarter_num = 1
GROUP BY d.full_date, d.day_name
ORDER BY d.full_date;

-- ---------------------------------------------------------------------
-- QUERY Q07b: ROLL-UP level 2 - WEEKLY room bookings (Q1 2024)
-- week_start_date = the Monday of each week
-- ---------------------------------------------------------------------
SELECT d.week_start_date,
       COUNT(*)                         AS bookings,
       ROUND(SUM(f.duration_hours), 1)  AS hours_booked,
       COUNT(DISTINCT d.full_date)      AS days_with_bookings
FROM fact_room_booking f
JOIN dim_date d ON d.date_key = f.date_key
WHERE d.year_num = 2024 AND d.quarter_num = 1
GROUP BY d.week_start_date
ORDER BY d.week_start_date;

-- ---------------------------------------------------------------------
-- QUERY Q07c: ROLL-UP level 3 - MONTHLY room bookings (all of 2024)
-- ---------------------------------------------------------------------
SELECT d.month_label,
       COUNT(*)                                          AS bookings,
       ROUND(SUM(f.duration_hours), 1)                   AS hours_booked,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT d.full_date), 1) AS avg_bookings_per_active_day
FROM fact_room_booking f
JOIN dim_date d ON d.date_key = f.date_key
WHERE d.year_num = 2024
GROUP BY d.month_label
ORDER BY d.month_label;

-- ---------------------------------------------------------------------
-- QUERY Q07d: ROLL-UP in ONE result: weeks + month subtotals + grand total
-- Technique : three GROUP BY levels glued together with UNION ALL
--             (this is what GROUP BY ... WITH ROLLUP does in MySQL;
--             SQLite does not have ROLLUP, so we write the levels out)
-- Read it as: level = 'week' rows add up to the 'MONTH TOTAL' row,
--             and the months add up to the 'GRAND TOTAL' row (Q1 2024)
-- ---------------------------------------------------------------------
WITH q1 AS (
    SELECT d.month_label, d.week_start_date, f.duration_hours
    FROM fact_room_booking f
    JOIN dim_date d ON d.date_key = f.date_key
    WHERE d.year_num = 2024 AND d.quarter_num = 1
)
SELECT * FROM (
    SELECT month_label, week_start_date, 'week' AS level,
           COUNT(*) AS bookings, ROUND(SUM(duration_hours), 1) AS hours_booked
    FROM q1 GROUP BY month_label, week_start_date
    UNION ALL
    SELECT month_label, NULL, 'MONTH TOTAL',
           COUNT(*), ROUND(SUM(duration_hours), 1)
    FROM q1 GROUP BY month_label
    UNION ALL
    SELECT NULL, NULL, 'GRAND TOTAL',
           COUNT(*), ROUND(SUM(duration_hours), 1)
    FROM q1
)
ORDER BY month_label IS NULL, month_label, week_start_date IS NULL, week_start_date;


-- ---------------------------------------------------------------------
-- QUERY Q08a: SLICING - only Q1 2024
-- Question  : Show the data for one specific time period
-- Technique : SLICE = fix ONE dimension to one value (time = Q1 2024)
--             and look at the rest of the cube
-- ---------------------------------------------------------------------
SELECT u.service,
       SUM(u.usage_count)                AS total_usage,
       COUNT(DISTINCT u.date_key)        AS active_days,
       ROUND(1.0 * SUM(u.usage_count) / COUNT(DISTINCT u.date_key), 1) AS avg_per_active_day
FROM v_usage_cube u
JOIN dim_date d ON d.date_key = u.date_key
WHERE d.year_num = 2024 AND d.quarter_name = 'Q1'          -- <== the slice
GROUP BY u.service
ORDER BY u.service;

-- ---------------------------------------------------------------------
-- QUERY Q08b: SLICING - Q1 2024 broken down by department
-- ---------------------------------------------------------------------
SELECT dp.department_name,
       SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
       SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads,
       SUM(CASE WHEN u.service = 'Room Bookings'     THEN u.usage_count ELSE 0 END) AS room_bookings
FROM v_usage_cube u
JOIN dim_date d        ON d.date_key = u.date_key
JOIN dim_department dp ON dp.department_key = u.department_key
WHERE d.year_num = 2024 AND d.quarter_name = 'Q1'
GROUP BY dp.department_name
ORDER BY dp.department_name;


-- ---------------------------------------------------------------------
-- QUERY Q09a: DICING - Engineering + digital downloads + March 2024
-- Question  : Engineering students' digital downloads in March
-- Technique : DICE = filter on SEVERAL dimensions at the same time
--             (department AND date AND user type) -> a smaller sub-cube
-- ---------------------------------------------------------------------
SELECT r.resource_type,
       ut.user_type,
       SUM(f.download_count)               AS downloads,
       ROUND(AVG(f.duration_minutes), 0)   AS avg_reading_minutes
FROM fact_digital_usage f
JOIN dim_date d        ON d.date_key = f.date_key
JOIN dim_department dp ON dp.department_key = f.department_key
JOIN dim_resource r    ON r.resource_key = f.resource_key
JOIN dim_user_type ut  ON ut.user_type_key = f.user_type_key
WHERE dp.department_code = 'ENG'                -- dimension 1: department
  AND d.month_label = '2024-03'                 -- dimension 2: time
  AND ut.user_group = 'Student'                 -- dimension 3: user type
GROUP BY r.resource_type, ut.user_type
ORDER BY downloads DESC;

-- ---------------------------------------------------------------------
-- QUERY Q09b: DICING - (CS + Engineering) x (Journal + E-book) x (Q1 2024)
-- ---------------------------------------------------------------------
SELECT dp.department_name,
       r.resource_type,
       d.month_name,
       SUM(f.download_count) AS downloads
FROM fact_digital_usage f
JOIN dim_date d        ON d.date_key = f.date_key
JOIN dim_department dp ON dp.department_key = f.department_key
JOIN dim_resource r    ON r.resource_key = f.resource_key
WHERE dp.department_code IN ('CS', 'ENG')
  AND r.resource_type IN ('Journal', 'E-book')
  AND d.year_num = 2024 AND d.quarter_num = 1
GROUP BY dp.department_name, r.resource_type, d.month_num, d.month_name
ORDER BY dp.department_name, r.resource_type, d.month_num;


-- ---------------------------------------------------------------------
-- QUERY Q10a: PIVOT - resource types across departments (matrix)
-- Question  : Compare resource types across departments
-- Technique : PIVOT = turn the values of one dimension (resource type)
--             into COLUMNS, departments stay as ROWS
-- ---------------------------------------------------------------------
SELECT dp.department_name,
       SUM(CASE WHEN r.resource_type = 'E-book'  THEN f.download_count ELSE 0 END) AS e_books,
       SUM(CASE WHEN r.resource_type = 'Journal' THEN f.download_count ELSE 0 END) AS journals,
       SUM(CASE WHEN r.resource_type = 'Article' THEN f.download_count ELSE 0 END) AS articles,
       SUM(f.download_count)                                                       AS row_total,
       ROUND(100.0 * SUM(CASE WHEN r.resource_type = 'Journal' THEN f.download_count ELSE 0 END)
             / SUM(f.download_count), 1)                                           AS journal_share_pct
FROM fact_digital_usage f
JOIN dim_department dp ON dp.department_key = f.department_key
JOIN dim_resource r    ON r.resource_key = f.resource_key
GROUP BY dp.department_name
ORDER BY row_total DESC;

-- ---------------------------------------------------------------------
-- QUERY Q10b: PIVOT - library services (columns) by department (rows) per year
-- ---------------------------------------------------------------------
SELECT dp.department_name,
       SUM(CASE WHEN d.year_num = 2023 AND u.service = 'Book Loans' THEN u.usage_count ELSE 0 END) AS loans_2023,
       SUM(CASE WHEN d.year_num = 2025 AND u.service = 'Book Loans' THEN u.usage_count ELSE 0 END) AS loans_2025,
       SUM(CASE WHEN d.year_num = 2023 AND u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS downloads_2023,
       SUM(CASE WHEN d.year_num = 2025 AND u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS downloads_2025,
       SUM(CASE WHEN d.year_num = 2023 AND u.service = 'Room Bookings' THEN u.usage_count ELSE 0 END) AS rooms_2023,
       SUM(CASE WHEN d.year_num = 2025 AND u.service = 'Room Bookings' THEN u.usage_count ELSE 0 END) AS rooms_2025
FROM v_usage_cube u
JOIN dim_date d        ON d.date_key = u.date_key
JOIN dim_department dp ON dp.department_key = u.department_key
WHERE dp.department_code <> 'UNK'
GROUP BY dp.department_name
ORDER BY dp.department_name;


-- =====================================================================
--                    LEVEL 3 - ADVANCED ANALYTICS (BONUS)
-- =====================================================================

-- ---------------------------------------------------------------------
-- QUERY Q11: CORRELATION - do more book loans go with more journal downloads?
-- Technique : Pearson correlation r calculated in SQL from sums
--             r = (n*Sxy - Sx*Sy) / sqrt((n*Sxx - Sx^2) * (n*Syy - Sy^2))
-- Read it as: r near +1 = strong positive link, 0 = no link, -1 = opposite
-- SQLITE NOTE: SQRT() needs SQLite 3.35+ with math functions (DB Browser
--             for SQLite 3.12+, Python 3.12+). run_business_queries.py adds
--             SQRT itself if your SQLite does not have it.
-- LIMITATION: the Digital Resources System does not record StudentID,
--             so we cannot correlate per STUDENT. We use department-month
--             pairs instead (8 departments x 36 months).
-- ---------------------------------------------------------------------
WITH loans AS (
    SELECT f.department_key, d.month_label, SUM(f.loan_count) AS x
    FROM fact_book_loan f JOIN dim_date d ON d.date_key = f.checkout_date_key
    GROUP BY f.department_key, d.month_label
),
journals AS (
    SELECT f.department_key, d.month_label, SUM(f.download_count) AS y
    FROM fact_digital_usage f
    JOIN dim_date d     ON d.date_key = f.date_key
    JOIN dim_resource r ON r.resource_key = f.resource_key
    WHERE r.resource_type = 'Journal'
    GROUP BY f.department_key, d.month_label
),
pairs AS (
    SELECT l.department_key, l.month_label, l.x, COALESCE(j.y, 0) AS y
    FROM loans l
    LEFT JOIN journals j ON j.department_key = l.department_key AND j.month_label = l.month_label
    WHERE l.department_key <> 1
)
SELECT COUNT(*) AS department_month_pairs,
       ROUND((COUNT(*) * SUM(x * y) - SUM(x) * SUM(y))
             / SQRT((COUNT(*) * SUM(x * x) - SUM(x) * SUM(x))
                  * (COUNT(*) * SUM(y * y) - SUM(y) * SUM(y))), 3) AS pearson_r
FROM pairs;


-- ---------------------------------------------------------------------
-- QUERY Q12: FORECAST - digital downloads for the first 6 months of 2026
-- Technique : simple linear regression (trend line y = a + b*t) in SQL,
--             t = month number 1..36. The forecast continues the line.
-- Read it as: slope = extra downloads per month. A trend line ignores
--             seasonality (exam peaks), so treat it as a planning guide.
--             (forecast.py in this folder adds seasonality.)
-- ---------------------------------------------------------------------
WITH monthly AS (
    SELECT d.month_label,
           ROW_NUMBER() OVER (ORDER BY d.month_label) AS t,
           SUM(f.download_count)                      AS y
    FROM fact_digital_usage f
    JOIN dim_date d ON d.date_key = f.date_key
    GROUP BY d.month_label
),
fit AS (
    SELECT 1.0 * (COUNT(*) * SUM(t * y) - SUM(t) * SUM(y)) / (COUNT(*) * SUM(t * t) - SUM(t) * SUM(t)) AS slope,
           AVG(y) AS mean_y, AVG(t) AS mean_t, COUNT(*) AS n
    FROM monthly
),
future AS (
    SELECT DISTINCT month_label, month_num FROM dim_date
    WHERE year_num = 2026 AND month_num <= 6
)
SELECT fu.month_label                                               AS forecast_month,
       ROUND(fi.mean_y + fi.slope * ((fi.n + fu.month_num) - fi.mean_t), 0) AS forecast_downloads,
       ROUND(fi.slope, 2)                                           AS slope_per_month
FROM future fu
CROSS JOIN fit fi
ORDER BY fu.month_label;


-- ---------------------------------------------------------------------
-- QUERY Q13: ANOMALY DETECTION - sudden drops in digital downloads
-- Technique : 3 steps with window functions
--   1. seasonal index = month / average month of THAT year
--      (removes the yearly growth: 1.30 = 30% busier than a normal month)
--   2. normal index   = average index of the same calendar month in the
--      OTHER years (holiday dips are normal every year, so not flagged)
--   3. compare the two
-- Read it as: index below 50% of normal = ANOMALY - sudden drop
--             index above 200% of normal = ANOMALY - unusual spike
-- ---------------------------------------------------------------------
WITH monthly AS (
    SELECT d.month_label, d.year_num, d.month_num, SUM(f.download_count) AS downloads
    FROM fact_digital_usage f
    JOIN dim_date d ON d.date_key = f.date_key
    GROUP BY d.month_label, d.year_num, d.month_num
),
indexed AS (
    SELECT month_label, month_num, downloads,
           1.0 * downloads / AVG(downloads) OVER (PARTITION BY year_num) AS seasonal_index
    FROM monthly
),
compared AS (
    SELECT month_label, downloads, seasonal_index,
           (SUM(seasonal_index) OVER (PARTITION BY month_num) - seasonal_index)
             / (COUNT(*) OVER (PARTITION BY month_num) - 1)       AS normal_index
    FROM indexed
)
SELECT month_label,
       downloads,
       ROUND(seasonal_index, 2)                                             AS seasonal_index,
       ROUND(normal_index, 2)                                               AS normal_index,
       ROUND(100.0 * (seasonal_index - normal_index) / normal_index, 1)    AS change_pct,
       CASE WHEN seasonal_index < 0.5 * normal_index THEN 'ANOMALY - sudden drop'
            WHEN seasonal_index > 2.0 * normal_index THEN 'ANOMALY - unusual spike'
            ELSE 'normal' END                                               AS status
FROM compared
ORDER BY month_label;


-- =====================================================================
--                    EXTRA QUERIES (other questions from section 2)
-- =====================================================================

-- ---------------------------------------------------------------------
-- QUERY Q14: Are digital resources replacing physical books?
-- Technique : yearly totals + ratio + growth vs previous year (LAG)
-- ---------------------------------------------------------------------
WITH yearly AS (
    SELECT d.year_num,
           SUM(CASE WHEN u.service = 'Book Loans'        THEN u.usage_count ELSE 0 END) AS book_loans,
           SUM(CASE WHEN u.service = 'Digital Downloads' THEN u.usage_count ELSE 0 END) AS digital_downloads
    FROM v_usage_cube u
    JOIN dim_date d ON d.date_key = u.date_key
    GROUP BY d.year_num
)
SELECT year_num, book_loans, digital_downloads,
       ROUND(1.0 * digital_downloads / book_loans, 1)                               AS downloads_per_loan,
       ROUND(100.0 * (book_loans - LAG(book_loans) OVER (ORDER BY year_num))
             / LAG(book_loans) OVER (ORDER BY year_num), 1)                          AS loans_growth_pct,
       ROUND(100.0 * (digital_downloads - LAG(digital_downloads) OVER (ORDER BY year_num))
             / LAG(digital_downloads) OVER (ORDER BY year_num), 1)                   AS downloads_growth_pct
FROM yearly
ORDER BY year_num;


-- ---------------------------------------------------------------------
-- QUERY Q15: Which study rooms are most popular - and WHY?
-- Technique : facts joined to room attributes; utilisation =
--             hours booked / hours available (6 slots x 2 h x 1096 days)
-- Read it as: compare bookings with capacity, projector, quiet zone
-- ---------------------------------------------------------------------
SELECT rm.room_number, rm.room_type, rm.capacity,
       CASE WHEN rm.has_projector = 1 THEN 'Yes' ELSE 'No' END AS projector,
       CASE WHEN rm.is_quiet_zone = 1 THEN 'Yes' ELSE 'No' END AS quiet_zone,
       COUNT(*)                                              AS bookings,
       ROUND(SUM(f.duration_hours), 0)                       AS hours_booked,
       ROUND(100.0 * SUM(f.duration_hours) / (12 * 1096), 1) AS utilisation_pct,
       ROUND(100.0 * SUM(CASE WHEN p.purpose_group = 'Collaborative' THEN 1 ELSE 0 END)
             / COUNT(*), 0)                                  AS group_work_pct,
       RANK() OVER (ORDER BY COUNT(*) DESC)                  AS popularity_rank
FROM fact_room_booking f
JOIN dim_room rm             ON rm.room_key = f.room_key
JOIN dim_booking_purpose p   ON p.purpose_key = f.purpose_key
GROUP BY rm.room_number, rm.room_type, rm.capacity, rm.has_projector, rm.is_quiet_zone
ORDER BY popularity_rank;


-- ---------------------------------------------------------------------
-- QUERY Q16: Undergraduate vs graduate usage patterns
-- Technique : the same student dimension used by two fact tables
--             (conformed dimension) + the user-type dimension
-- ---------------------------------------------------------------------
SELECT s.student_level,
       COUNT(DISTINCT s.student_key)                     AS active_students,
       COUNT(*)                                          AS book_loans,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT s.student_key), 1) AS loans_per_student,
       ROUND(AVG(f.loan_duration_days), 1)               AS avg_loan_days,
       ROUND(100.0 * SUM(f.is_overdue) / COUNT(*), 1)    AS overdue_pct,
       ROUND(100.0 * SUM(CASE WHEN b.book_category = 'Research' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                              AS research_books_pct
FROM fact_book_loan f
JOIN dim_student s ON s.student_key = f.student_key
JOIN dim_book b    ON b.book_key = f.book_key
WHERE s.student_level IN ('Undergraduate', 'Graduate')
GROUP BY s.student_level;

-- ---------------------------------------------------------------------
-- QUERY Q17: Undergraduate vs graduate - digital resources
-- ---------------------------------------------------------------------
SELECT ut.user_type,
       SUM(f.download_count)                                                       AS downloads,
       ROUND(100.0 * SUM(CASE WHEN r.resource_type = 'Journal' THEN f.download_count ELSE 0 END)
             / SUM(f.download_count), 1)                                           AS journal_pct,
       ROUND(100.0 * SUM(CASE WHEN r.resource_type = 'E-book' THEN f.download_count ELSE 0 END)
             / SUM(f.download_count), 1)                                           AS ebook_pct,
       ROUND(AVG(f.duration_minutes), 0)                                           AS avg_reading_minutes
FROM fact_digital_usage f
JOIN dim_user_type ut ON ut.user_type_key = f.user_type_key
JOIN dim_resource r   ON r.resource_key = f.resource_key
GROUP BY ut.user_type
ORDER BY downloads DESC;


-- ---------------------------------------------------------------------
-- QUERY Q18: Operational - books still not returned (oldest first)
-- Question  : Which loans should the desk follow up? (masked IDs only)
-- ---------------------------------------------------------------------
SELECT s.student_id_masked,
       b.title,
       d.full_date                                  AS checkout_date,
       CAST(julianday('2025-12-31') - julianday(d.full_date) AS INTEGER) AS days_out_at_end_of_data
FROM fact_book_loan f
JOIN dim_date d    ON d.date_key = f.checkout_date_key
JOIN dim_student s ON s.student_key = f.student_key
JOIN dim_book b    ON b.book_key = f.book_key
WHERE f.is_returned = 0
ORDER BY d.full_date
LIMIT 15;


-- ---------------------------------------------------------------------
-- QUERY Q19: Data quality check - proof that the warehouse has no duplicates
-- Read it as: every "duplicates" column must be 0
-- ---------------------------------------------------------------------
SELECT 'fact_book_loan'    AS fact_table, COUNT(*) AS total_rows,
       COUNT(*) - COUNT(DISTINCT transaction_id) AS duplicates
FROM fact_book_loan
UNION ALL
SELECT 'fact_room_booking', COUNT(*), COUNT(*) - COUNT(DISTINCT booking_id)
FROM fact_room_booking
UNION ALL
SELECT 'fact_room_booking (room+date+slot)', COUNT(*),
       COUNT(*) - COUNT(DISTINCT room_key || '-' || date_key || '-' || time_slot_key)
FROM fact_room_booking;
