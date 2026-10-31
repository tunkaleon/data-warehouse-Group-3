"""
=====================================================================
 build_database.py  -  create the SQLite data warehouse in one step
=====================================================================
 Runs the SQL scripts of this folder in the right order:

   01_create_database.sql        reset (drop old tables)
   02_create_staging_tables.sql  staging area + cleansing rules + ETL logs
   03_create_dimension_tables.sql 9 dimensions (dates 2023-2027 included)
   04_create_fact_tables.sql     3 fact tables + OLAP cube view
   05_create_indexes.sql         indexes
   06_security_rbac.sql          roles, permissions, users table, masked views
   07_audit_logging.sql          audit table + triggers
   sample_data.sql               (only with --with-data) the loaded data

 HOW TO RUN (from this folder)
     python build_database.py               -> empty warehouse, ready for the ETL
     python build_database.py --with-data   -> also load sample_data.sql

 Python already contains SQLite, so nothing has to be installed.
 The result is the file library_dw.db (open it with DB Browser for SQLite).
=====================================================================
"""
import os
import sys
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(HERE, "library_dw.db")
SCRIPTS = ["01_create_database.sql", "02_create_staging_tables.sql", "03_create_dimension_tables.sql",
           "04_create_fact_tables.sql", "05_create_indexes.sql", "06_security_rbac.sql",
           "07_audit_logging.sql"]


def build(with_data=False, db_file=DB_FILE):
    scripts = SCRIPTS + (["sample_data.sql"] if with_data else [])
    con = sqlite3.connect(db_file)
    con.execute("PRAGMA foreign_keys = ON")
    for name in scripts:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            sql = f.read()
        try:
            con.executescript(sql)          # runs every statement of the file
            print(f"  OK   {name}")
        except sqlite3.Error as e:
            con.rollback()
            con.close()
            raise SystemExit(f"  FAILED in {name}: {e}")
    con.commit()

    # Show what was created
    print(f"\nDatabase: {db_file}  (SQLite {sqlite3.sqlite_version})")
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        print(f"  {t:24s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>6} rows")
    problems = con.execute("PRAGMA foreign_key_check").fetchall()
    print(f"\nForeign key problems: {len(problems)}")
    con.close()


if __name__ == "__main__":
    build(with_data="--with-data" in sys.argv)
