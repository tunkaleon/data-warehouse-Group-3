# University Library Analytics - Data Warehouse (FA1 Group Project)

HAIP · Data Mining and Data Warehousing · Group **X** (rename the folder and the zip to your group number, e.g. `Group03_LibraryDW`)

A complete data warehouse that combines the library's three systems (book lending, digital resources, study rooms), cleans the data automatically, and answers the business questions with SQL, OLAP and Power BI dashboards. It is secured with role-based access and has a tested backup and recovery plan.

**Database:** SQLite (one file: `03_Database_Files/library_dw.db`) · **ETL:** Python + pandas · **Dashboards:** Power BI Desktop

---

## Quick start (5 minutes)

```bash
# 1. once: install Python 3.10+ (python.org), then the libraries
pip install pandas openpyxl matplotlib cryptography

# 2. rebuild EVERYTHING from scratch (data, database, ETL, queries, charts, tests) - about 5 seconds
python run_all.py
```

Then:
* open `03_Database_Files/library_dw.db` with **DB Browser for SQLite** (free) to see the tables;
* open `05_Analytics_Package/query_results.xlsx` to see the answers to all business questions;
* follow `06_Dashboards/dashboard_guide.pdf` to build the Power BI dashboards.

## Step by step (what each part does)

| Step | Run (from the folder) | What happens |
|---|---|---|
| 1. Source data | `09_Source_Data> python generate_source_data.py` | creates the 3 messy source files (all data problems of the brief) |
| 2. Database | `03_Database_Files> python build_database.py` | runs SQL scripts 01-07 → empty warehouse `library_dw.db` |
| 3. ETL | `04_ETL_Files> python etl_script.py` | extract → clean (30 rules) → validate (12 checks) → load; writes `sample_data.sql`, error log, Power BI CSVs |
| 4. Users | `07_Security_Documentation/security_tools> python secure_access.py --setup` | creates the 10 demo users (hashed passwords) |
| 5. Queries | `05_Analytics_Package> python run_business_queries.py` | runs the 31 queries → `query_results.xlsx` |
| 6. Bonus | `05_Analytics_Package> python advanced_analytics.py` | correlation, forecast 2026, anomaly detection |
| 7. Dashboards | `06_Dashboards> python build_dashboard_images.py` | dashboard design images; Power BI: see the guide |
| 8. Security test | `security_tools> python secure_access.py --demo` | shows what each role can and cannot do |
| 9. Backup test | `backup_scripts> python backup_restore.py full` then `verify` | backup + automatic restore test |
| 10. Web dashboards | `12_Web_Dashboard> python app.py` | login page + Executive / Department / Operational dashboards at http://127.0.0.1:5000 |

## Folder contents (submission structure)

```
GroupX_LibraryDW/
├── 01_Design_Document.pdf            architecture, ERD, ETL flowchart, schema justification, data dictionary
├── 01_Design/                         diagrams (PNG + Graphviz .dot sources)
├── 02_Final_Presentation.pptx         30-minute presentation with speaker notes
├── 03_Database_Files/                 SQL scripts 01-07, sample_data.sql, build_database.py, library_dw.db, README.md
├── 04_ETL_Files/                      etl_script.py, data_quality_report.pdf, transformation_rules.xlsx, error_log_sample.txt
├── 05_Analytics_Package/              business_queries.sql (31 queries), query_results.xlsx, olap_operations_demo.pdf, bonus analytics
├── 06_Dashboards/                     3 dashboard images, dashboard_guide.pdf, Power BI data + DAX + theme
├── 07_Security_Documentation/         RBAC_policy.pdf, security_implementation.pdf, backup_recovery_plan.pdf, tools + test results
├── 08_User_Guide.pdf                  for non-technical users
├── 09_Source_Data/                    book_transactions.csv, digital_usage.xlsx, room_bookings.csv (+ generator, reference files)
├── 10_Team_Contribution_Report.pdf    contributions, challenges, lessons learned (complete the names!)
├── 11_Editable_Documents/             Word (.docx) copies of every PDF - edit names/group number here
├── 12_Web_Dashboard/                  Flask web site: login + 3 role-based dashboards (see its README)
└── run_all.py                         rebuilds everything in order
```

## Before you submit - checklist

- [ ] Replace **Group X** and **Member 1/2/3** with your group number and names (in `11_Editable_Documents/*.docx`, then *File → Save as PDF* over the PDFs; in the presentation title slide and footer).
- [ ] Complete the percentages and personal reflections in the Team Contribution Report.
- [ ] Build the dashboards in Power BI and save your own screenshots as `06_Dashboards/*_dashboard.jpg` (and the `.pbix`).
- [ ] Rename the folder to `GroupNN_LibraryDW` and zip it as `GroupNN_LibraryDW.zip`.
- [ ] Upload to GitHub as repository `GroupNN` and put the link in the Google Drive. **Never upload `backup.key`** (the `.gitignore` already excludes it).

## Key results (sample data 2023-2025)

* 9,390 raw rows → 9,065 clean rows; 527 problems logged; **0 duplicates** in the warehouse
* Digital downloads +30% in 2025, book loans −13%: digital resources are replacing physical books
* Engineering and Computer Science use the library most; peak room time is Wednesday 14:00-16:00
* October 2024 downloads −57% vs a normal October: flagged automatically as an anomaly
* Restore test after deleting the database: all 26 tables identical
