# Security tools (SQLite)

SQLite has no user accounts, so people reach the warehouse through `secure_access.py`.

```
python secure_access.py --setup          # create the demo users (passwords stored as PBKDF2 hashes)
python secure_access.py --demo           # run all security tests (used in the presentation)
python secure_access.py --user head_cs   # log in and type SQL yourself
```

| User | Role | Can do |
|---|---|---|
| lib_admin | dw_admin | everything |
| etl_service | dw_etl | staging + warehouse tables, not security tables |
| director, analyst_amina, powerbi_reader | dw_analyst | read the whole warehouse, **not** the real StudentID, no staging, no changes |
| head_cs, head_eng, head_bus | dw_dept_head | read only their own department (private `my_*` tables) |
| backup_user | dw_backup | read everything for backups, no changes |

Demo passwords are listed in `secure_access.py` (DEMO_USERS). Change them before real use.
`security_test_results.txt` shows the output of `--demo`.
