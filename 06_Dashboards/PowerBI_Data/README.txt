PowerBI_Data - clean warehouse tables written by 04_ETL_Files/etl_script.py
==========================================================================
Use these CSV files in Power BI if you do not want to install the SQLite
ODBC driver (see dashboard_guide.pdf, Option B). They contain exactly the
same rows as library_dw.db, except:
  * dim_student has NO real student_id column (only student_id_masked)
  * dim_date row -1 (1900-01-01, "not returned") is included; filter it
    out in Power Query before marking dim_date as the date table.
powerbi_rls_users.csv: e-mail -> department, for Row-Level Security of
department heads in the Power BI service (replace the example e-mails).
Re-run the ETL to refresh these files; then press Refresh in Power BI.
