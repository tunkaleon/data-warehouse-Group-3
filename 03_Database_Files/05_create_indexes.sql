-- =====================================================================
-- Script 05: INDEXES                                    (SQLite 3)
-- ---------------------------------------------------------------------
-- SQLite automatically indexes every PRIMARY KEY and UNIQUE column.
-- Unlike MySQL it does NOT index foreign keys automatically, so we add
-- the indexes our joins and business questions need.
-- ("Which indexes did you create and why?" - stakeholder question 4)
-- =====================================================================

-- ---------- Dimension lookups ------------------------------------------
CREATE INDEX IF NOT EXISTS idx_student_id_current ON dim_student (student_id, is_current);  -- ETL lookups
CREATE INDEX IF NOT EXISTS idx_resource_type      ON dim_resource (resource_type);          -- Q4b, Q10
CREATE INDEX IF NOT EXISTS idx_book_category      ON dim_book (book_category);              -- Q5

-- ---------- dim_date: drill-down / roll-up paths -----------------------
-- Year -> Quarter -> Month -> Day   (Q6 drill-down)
CREATE INDEX IF NOT EXISTS idx_date_hierarchy ON dim_date (year_num, quarter_num, month_num, day_of_month);
-- Day -> Week -> Month              (Q7 roll-up)
CREATE INDEX IF NOT EXISTS idx_date_week      ON dim_date (week_start_date);
CREATE INDEX IF NOT EXISTS idx_date_month     ON dim_date (month_label);

-- ---------- fact_book_loan ---------------------------------------------
CREATE INDEX IF NOT EXISTS idx_loan_date       ON fact_book_loan (checkout_date_key);           -- Q1, Q6
CREATE INDEX IF NOT EXISTS idx_loan_dept_date  ON fact_book_loan (department_key, checkout_date_key);  -- Q2, Q5
CREATE INDEX IF NOT EXISTS idx_loan_book       ON fact_book_loan (book_key);                    -- Q4a top books
CREATE INDEX IF NOT EXISTS idx_loan_student    ON fact_book_loan (student_key);                 -- Q16 UG vs Grad

-- ---------- fact_digital_usage -----------------------------------------
CREATE INDEX IF NOT EXISTS idx_dig_date_dept   ON fact_digital_usage (date_key, department_key);    -- Q1, Q9 dice
CREATE INDEX IF NOT EXISTS idx_dig_dept_res    ON fact_digital_usage (department_key, resource_key); -- Q10 pivot
CREATE INDEX IF NOT EXISTS idx_dig_resource    ON fact_digital_usage (resource_key);                 -- Q4b journals
CREATE INDEX IF NOT EXISTS idx_dig_usertype    ON fact_digital_usage (user_type_key);                -- Q17

-- ---------- fact_room_booking ------------------------------------------
CREATE INDEX IF NOT EXISTS idx_room_date_slot  ON fact_room_booking (date_key, time_slot_key);  -- Q3 peak times
CREATE INDEX IF NOT EXISTS idx_room_dept       ON fact_room_booking (department_key);           -- Q2
CREATE INDEX IF NOT EXISTS idx_room_student    ON fact_room_booking (student_key);              -- Q16

-- List every index in the database
SELECT tbl_name AS table_name, name AS index_name
FROM sqlite_master
WHERE type = 'index' AND name LIKE 'idx_%'
ORDER BY tbl_name, name;
