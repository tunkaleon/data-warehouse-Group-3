@echo off
REM ====================================================================
REM  schedule_backups.bat - register the data refresh and the backups
REM  in Windows Task Scheduler. Run ONCE (right-click > Run as administrator).
REM
REM   Daily 00:30          nightly ETL + DIFFERENTIAL backup (run_nightly_etl.bat)
REM   Sunday 01:00         FULL backup, encrypted
REM   Every 4 h, 08-20 h   INCREMENTAL backup (audit log, security changes)
REM ====================================================================
set HERE=%~dp0
set ETL=%HERE%..\..\04_ETL_Files\run_nightly_etl.bat

schtasks /create /tn "LibraryDW Nightly ETL" /tr "\"%ETL%\"" /sc daily /st 00:30 /f
schtasks /create /tn "LibraryDW Full Backup" /tr "python \"%HERE%backup_restore.py\" full --encrypt" /sc weekly /d SUN /st 01:00 /f
schtasks /create /tn "LibraryDW Incremental Backup" /tr "python \"%HERE%backup_restore.py\" incremental" /sc daily /st 08:00 /ri 240 /du 12:00 /f

echo Done. Open "Task Scheduler" to see the three LibraryDW tasks.
