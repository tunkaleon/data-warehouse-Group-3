# Backup and recovery tools (SQLite)

| Command (run in this folder) | What it does |
|---|---|
| `python backup_restore.py full --encrypt` | Full copy of `library_dw.db` (online backup API) + integrity check + SHA-256 + AES encryption |
| `python backup_restore.py differential` | Everything changed since the last **full** backup (SQL file) |
| `python backup_restore.py incremental` | Everything changed since the **last backup of any kind** (SQL file) |
| `python backup_restore.py list` | Show the backup catalogue |
| `python backup_restore.py verify` | **Restore test**: rebuild the newest chain in a scratch file, compare every table with the live database, PASS/FAIL |
| `python backup_restore.py restore latest` | Disaster recovery: newest full + newest differential + later incrementals |
| `schedule_backups.bat` | Registers the nightly ETL and the three backup jobs in Windows Task Scheduler |

* Encryption needs `pip install cryptography`. The key is saved in `backup.key` the first time.
  **Keep a copy of the key somewhere else** (USB stick in the director's safe). Without it, encrypted backups cannot be restored.
* Backups are written to `backups/`. In real use, point `BACKUP_DIR` (top of the script) to a second disk or a network share.
* `backup_test_results.txt` shows the output of the restore test and the disaster-recovery test.
