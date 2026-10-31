"""
=====================================================================
 run_business_queries.py
 Runs EVERY query of business_queries.sql on the SQLite warehouse and
 saves the results in query_results.xlsx (one sheet per query + Index).

 HOW TO RUN (from this folder)
     pip install pandas openpyxl
     python run_business_queries.py
=====================================================================
"""
import os
import re
import math
import sqlite3
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(os.path.dirname(HERE), "03_Database_Files", "library_dw.db")
SQL_FILE = os.path.join(HERE, "business_queries.sql")
XLSX_FILE = os.path.join(HERE, "query_results.xlsx")


def connect():
    con = sqlite3.connect(DB_FILE)
    try:
        con.execute("SELECT sqrt(4)")                    # SQLite 3.35+ has math functions
    except sqlite3.OperationalError:
        con.create_function("sqrt", 1, math.sqrt)        # older SQLite: add SQRT from Python
    return con


def split_queries(sql_text):
    """Cut the file into (id, title, question, sql) using the '-- QUERY Qxx:' headers."""
    queries = []
    blocks = re.split(r"\n-- -+\n(?=-- QUERY )", sql_text)
    for block in blocks:
        head = re.match(r"-- QUERY (Q\d+\w?): (.*)", block)
        if not head:
            continue
        question = re.search(r"-- Question\s*: (.*)", block)
        # keep only the SQL lines (drop comment lines), take the first statement
        sql_lines = [line for line in block.splitlines() if not line.strip().startswith("--")]
        statement = "\n".join(sql_lines).split(";")[0].strip()
        queries.append((head.group(1), head.group(2).strip(), question.group(1).strip() if question else "", statement))
    return queries


def main():
    con = connect()
    sql_text = open(SQL_FILE, encoding="utf-8").read()
    # 1. create the cube view (section 0 of the file)
    view_sql = re.search(r"DROP VIEW IF EXISTS v_usage_cube;.*?;.*?;", sql_text, re.S).group(0)
    con.executescript(view_sql)

    # 2. run every query
    results = []
    for qid, title, question, statement in split_queries(sql_text):
        df = pd.read_sql_query(statement, con)
        results.append((qid, title, question, df))
        print(f"  {qid:5s} {len(df):4d} rows  {title}")
    con.close()

    # 3. write the Excel file
    font = lambda **k: Font(name="Arial", **k)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    line = Side(style="thin", color="BFBFBF")
    wb = Workbook()
    index = wb.active
    index.title = "Index"
    index["A1"] = "University Library Analytics - Query Results"
    index["A1"].font = font(bold=True, size=14)
    index["A2"] = "Results of every query in business_queries.sql, run on library_dw.db. Click a sheet name to open it."
    index["A2"].font = font(italic=True, size=10)
    for col, name in enumerate(["Query", "Sheet", "Title", "Business question", "Rows"], 1):
        cell = index.cell(row=4, column=col, value=name)
        cell.font = font(bold=True, color="FFFFFF")
        cell.fill = header_fill

    for r, (qid, title, question, df) in enumerate(results, start=5):
        ws = wb.create_sheet(qid)
        ws["A1"] = f"{qid}: {title}"
        ws["A1"].font = font(bold=True, size=12)
        ws["A2"] = question or "See business_queries.sql"
        ws["A2"].font = font(italic=True, size=10, color="595959")
        ws["A3"] = "Back to Index"
        ws["A3"].hyperlink = "#Index!A1"
        ws["A3"].font = font(size=9, color="0563C1", underline="single")
        for c, name in enumerate(df.columns, 1):
            cell = ws.cell(row=5, column=c, value=name)
            cell.font = font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
            width = max([len(str(name))] + [len(str(v)) for v in df[name].head(200)])
            ws.column_dimensions[get_column_letter(c)].width = min(max(10, width + 2), 50)
        for i, row in enumerate(df.itertuples(index=False), start=6):
            is_total = "TOTAL" in " ".join(str(v) for v in row)
            for c, value in enumerate(row, 1):
                if isinstance(value, float) and math.isnan(value):
                    value = None
                cell = ws.cell(row=i, column=c, value=value)
                cell.font = font(size=10, bold=is_total)
                cell.border = Border(bottom=line)
                if isinstance(value, float):
                    cell.number_format = "#,##0.0"
                elif isinstance(value, int):
                    cell.number_format = "#,##0"
        ws.freeze_panes = "A6"
        index.cell(row=r, column=1, value=qid).font = font(size=10)
        link = index.cell(row=r, column=2, value=qid)
        link.hyperlink = f"#{qid}!A1"
        link.font = font(size=10, color="0563C1", underline="single")
        index.cell(row=r, column=3, value=title).font = font(size=10)
        index.cell(row=r, column=4, value=question).font = font(size=10)
        index.cell(row=r, column=5, value=len(df)).font = font(size=10)
    for col, width in zip("ABCDE", [8, 8, 60, 72, 7]):
        index.column_dimensions[col].width = width
    wb.save(XLSX_FILE)
    print(f"\nSaved {len(results)} query results -> query_results.xlsx")


if __name__ == "__main__":
    main()
