"""
=====================================================================
 backup_restore.py  -  BACKUP and RECOVERY for library_dw.db (SQLite)
=====================================================================
 Three kinds of backup:
   FULL         a complete, consistent copy of the database file, made
                with SQLite's online backup API (users may keep working).
   INCREMENTAL  only what changed since the LAST backup of any kind
                (new ETL batches + new audit / error-log rows), as SQL.
   DIFFERENTIAL everything that changed since the last FULL backup, as SQL.

 Every backup gets: an integrity check, a SHA-256 checksum, an entry in
 backups/backup_catalog.json and (optional) AES encryption.

 COMMANDS (run from this folder)
     python backup_restore.py full [--encrypt]
     python backup_restore.py incremental
     python backup_restore.py differential
     python backup_restore.py list
     python backup_restore.py restore latest      newest full + newest differential +
                                                  every later incremental
     python backup_restore.py restore <file.db>   one specific full backup
     python backup_restore.py verify              TEST: restore into a scratch file and
                                                  compare it with the live database

 Schedule (schedule_backups.bat): full every Sunday 01:00, incremental every
 day 01:30, and a full backup right after every ETL run.
 Encryption needs:  pip install cryptography
=====================================================================
"""

import sys
import json
import time
import shutil
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

HERE = Path(__file__).resolve().parent
DB_FILE = HERE.parent.parent / "03_Database_Files" / "library_dw.db"
BACKUP_DIR = HERE / "backups"                 # in real use: another disk or a network share
CATALOG = BACKUP_DIR / "backup_catalog.json"
KEY_FILE = HERE / "backup.key"                # keep this key SEPARATE from the backups!
KEEP_FULL_DAYS = 28

# Tables whose NEW rows are saved by incremental/differential backups
LOG_TABLES = {"etl_batch_log": "batch_id", "etl_error_log": "error_id", "audit_log": "audit_id"}
# Tables replaced completely when a new ETL batch was loaded since the base backup
WAREHOUSE_TABLES = ["dim_student", "dim_book", "dim_resource", "fact_book_loan",
                    "fact_digital_usage", "fact_room_booking", "stg_book_transactions",
                    "stg_digital_usage", "stg_room_bookings", "stg_student_master", "stg_book_catalog"]


# ---------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------
def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_catalog():
    return json.loads(CATALOG.read_text()) if CATALOG.exists() else []


def save_catalog(entries):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(entries, indent=2))


def high_water_marks(con):
    """The highest id of each log table = 'how far' this backup goes."""
    return {t: con.execute(f"SELECT COALESCE(MAX({c}), 0) FROM {t}").fetchone()[0] for t, c in LOG_TABLES.items()}


def row_counts(con):
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def fernet():
    """AES encryption (Fernet = AES-128-CBC + HMAC). Creates the key file the first time."""
    from cryptography.fernet import Fernet
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(Fernet.generate_key())
        print(f"  new encryption key saved in {KEY_FILE.name} - store a copy OFF this computer")
    return Fernet(KEY_FILE.read_bytes())


# ---------------------------------------------------------------------
# FULL backup
# ---------------------------------------------------------------------
def full_backup(encrypt=False):
    BACKUP_DIR.joinpath("full").mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / "full" / f"library_dw_full_{now_stamp()}.db"
    start = time.time()
    src = sqlite3.connect(DB_FILE)
    dst = sqlite3.connect(target)
    src.backup(dst)                       # SQLite online backup: consistent copy while in use
    dst.close()

    check = sqlite3.connect(target)
    ok = check.execute("PRAGMA integrity_check").fetchone()[0]
    marks, counts = high_water_marks(check), row_counts(check)
    check.close()
    src.close()
    if ok != "ok":
        target.unlink()
        sys.exit(f"FULL BACKUP FAILED integrity check: {ok}")

    entry = {"type": "full", "file": str(target.relative_to(HERE)), "created": datetime.now().isoformat(timespec="seconds"),
             "marks": marks, "row_counts": counts, "encrypted": False}
    if encrypt:
        enc = target.with_suffix(".db.enc")
        enc.write_bytes(fernet().encrypt(target.read_bytes()))
        target.unlink()
        target, entry["file"], entry["encrypted"] = enc, str(enc.relative_to(HERE)), True
    entry["sha256"] = sha256(target)
    entry["size_kb"] = target.stat().st_size // 1024
    catalog = load_catalog() + [entry]
    save_catalog(remove_old_backups(catalog))
    print(f"FULL backup OK: {entry['file']}  ({entry['size_kb']} KB, {time.time() - start:.1f} s, "
          f"integrity ok{', encrypted' if encrypt else ''})")
    return entry


def remove_old_backups(catalog):
    """Retention: delete full backups older than KEEP_FULL_DAYS (always keep the newest)."""
    limit = datetime.now() - timedelta(days=KEEP_FULL_DAYS)
    fulls = [e for e in catalog if e["type"] == "full"]
    keep = []
    for e in catalog:
        if e["type"] == "full" and e is not fulls[-1] and datetime.fromisoformat(e["created"]) < limit:
            (HERE / e["file"]).unlink(missing_ok=True)
            print(f"  retention: deleted {e['file']}")
            continue
        keep.append(e)
    return keep


# ---------------------------------------------------------------------
# INCREMENTAL / DIFFERENTIAL backup (SQL file with only the changes)
# ---------------------------------------------------------------------
def sql_literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def insert_sql(con, table, where="1=1"):
    cur = con.execute(f"SELECT * FROM {table} WHERE {where}")
    cols = [d[0] for d in cur.description]
    return [f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES "
            f"({', '.join(sql_literal(v) for v in row)});" for row in cur]


def change_backup(kind):
    catalog = load_catalog()
    fulls = [e for e in catalog if e["type"] == "full"]
    if not fulls:
        sys.exit("No full backup yet - run:  python backup_restore.py full")
    base = catalog[-1] if kind == "incremental" else fulls[-1]     # what we compare with
    con = sqlite3.connect(DB_FILE)
    marks = high_water_marks(con)
    lines = [f"-- {kind.upper()} backup of library_dw.db, {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"-- changes since: {base['type']} backup {base['file']} ({base['created']})",
             "PRAGMA foreign_keys = OFF;", "BEGIN TRANSACTION;",
             # marker row: while a batch is 'RUNNING' the audit triggers stay quiet,
             # so replaying the backup does not create thousands of audit rows
             "INSERT OR REPLACE INTO etl_batch_log (batch_id, load_type, status, notes) "
             "VALUES (-1, 'FULL', 'RUNNING', 'restore in progress');"]
    new_batch = marks["etl_batch_log"] > base["marks"]["etl_batch_log"]
    if new_batch:
        # a new ETL batch replaced the warehouse: save the new contents of those tables
        lines.append("-- new ETL batch since the base backup: warehouse tables replaced")
        for t in WAREHOUSE_TABLES:
            lines.append(f"DELETE FROM {t};")
            lines.extend(insert_sql(con, t))
    for t, col in LOG_TABLES.items():
        lines.extend(insert_sql(con, t, f"{col} > {base['marks'][t]}"))
    lines += ["DELETE FROM etl_batch_log WHERE batch_id = -1;", "COMMIT;", "PRAGMA foreign_keys = ON;"]
    changes = sum(1 for line in lines if line.startswith("INSERT INTO") or
                  (line.startswith("INSERT OR REPLACE") and "batch_id = -1" not in line and "(-1, " not in line))
    con.close()

    folder = BACKUP_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"library_dw_{kind}_{now_stamp()}.sql"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entry = {"type": kind, "file": str(target.relative_to(HERE)), "created": datetime.now().isoformat(timespec="seconds"),
             "base": base["file"], "marks": marks, "changed_rows": changes, "sha256": sha256(target),
             "size_kb": max(1, target.stat().st_size // 1024)}
    save_catalog(catalog + [entry])
    print(f"{kind.upper()} backup OK: {entry['file']}  ({changes} changed rows"
          f"{', includes a new ETL batch' if new_batch else ''})")
    return entry


# ---------------------------------------------------------------------
# RESTORE
# ---------------------------------------------------------------------
def restore_chain(target, which="latest"):
    """Rebuild a database at 'target' from a full backup (+ later incrementals for 'latest')."""
    catalog = load_catalog()
    if which == "latest":
        # standard recovery chain:
        #   newest FULL  ->  newest DIFFERENTIAL after it (if any)  ->  every INCREMENTAL after that
        start = max(i for i, e in enumerate(catalog) if e["type"] == "full")
        chain = [catalog[start]]
        diffs = [i for i, e in enumerate(catalog) if i > start and e["type"] == "differential"]
        if diffs:
            start = diffs[-1]
            chain.append(catalog[start])
        chain += [e for e in catalog[start + 1:] if e["type"] == "incremental"]
    else:
        chain = [e for e in catalog if Path(e["file"]).name == Path(which).name]
        if not chain:
            sys.exit(f"{which} is not in the backup catalog")
    full = chain[0]
    source = HERE / full["file"]
    if sha256(source) != full["sha256"]:                    # damaged or changed backup file?
        sys.exit(f"CHECKSUM MISMATCH - {source.name} is damaged. Use an older backup.")
    data = source.read_bytes()
    if full.get("encrypted"):
        data = fernet().decrypt(data)
    Path(target).write_bytes(data)

    con = sqlite3.connect(target)
    for inc in chain[1:]:                                   # differential / incrementals, in order
        path = HERE / inc["file"]
        if sha256(path) != inc["sha256"]:
            sys.exit(f"CHECKSUM MISMATCH - {path.name} is damaged.")
        con.executescript(path.read_text(encoding="utf-8"))
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    return chain, ok


def restore(which):
    start = time.time()
    if DB_FILE.exists():
        safety = DB_FILE.with_name(f"library_dw_before_restore_{now_stamp()}.db")
        shutil.copy2(DB_FILE, safety)
        print(f"  current database saved as {safety.name} (just in case)")
    tmp = DB_FILE.with_suffix(".restoring")
    chain, ok = restore_chain(tmp, which)
    if ok != "ok":
        tmp.unlink()
        sys.exit(f"RESTORE FAILED integrity check: {ok}")
    tmp.replace(DB_FILE)                                    # switch only when everything is fine
    print(f"RESTORE OK from {[Path(e['file']).name for e in chain]} in {time.time() - start:.1f} s")


def verify():
    """Backup TEST: restore the newest chain into a scratch file and compare with the live database."""
    print("=" * 70)
    print(" BACKUP RESTORE TEST")
    print("=" * 70)
    start = time.time()
    scratch = BACKUP_DIR / "restore_test.db"
    chain, ok = restore_chain(scratch, "latest")
    seconds = time.time() - start
    live, restored = sqlite3.connect(DB_FILE), sqlite3.connect(scratch)
    a, b = row_counts(live), row_counts(restored)
    totals = "SELECT (SELECT SUM(loan_count) FROM fact_book_loan), (SELECT SUM(download_count) FROM fact_digital_usage)"
    sums_live, sums_restored = live.execute(totals).fetchone(), restored.execute(totals).fetchone()
    live.close()
    restored.close()
    scratch.unlink()

    print(f" restored from : {', '.join(Path(e['file']).name for e in chain)}")
    print(f" integrity     : {ok}")
    print(f" restore time  : {seconds:.2f} s")
    print(f"\n {'table':24s} {'live':>8s} {'restored':>9s}  result")
    all_ok = ok == "ok"
    for t in sorted(set(a) | set(b)):
        same = a.get(t) == b.get(t)
        all_ok &= same
        print(f" {t:24s} {a.get(t, '-'):>8} {b.get(t, '-'):>9}  {'PASS' if same else 'FAIL'}")
    same_sums = sums_live == sums_restored
    all_ok &= same_sums
    print(f"\n total loans / downloads: live {sums_live}, restored {sums_restored}  {'PASS' if same_sums else 'FAIL'}")
    print(f"\n RESULT: {'PASS - the backup can be restored completely' if all_ok else 'FAIL - investigate!'}")
    return all_ok


def list_backups():
    for e in load_catalog():
        print(f"{e['created']}  {e['type']:12s} {e['size_kb']:>6} KB  {e['file']}")


if __name__ == "__main__":
    if not DB_FILE.exists() and sys.argv[1:2] != ["restore"]:
        sys.exit(f"Database not found: {DB_FILE}")
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "full":
        full_backup(encrypt="--encrypt" in sys.argv)
    elif command in ("incremental", "differential"):
        change_backup(command)
    elif command == "restore" and len(sys.argv) > 2:
        restore(sys.argv[2])
    elif command == "verify":
        sys.exit(0 if verify() else 1)
    elif command == "list":
        list_backups()
    else:
        print(__doc__)
