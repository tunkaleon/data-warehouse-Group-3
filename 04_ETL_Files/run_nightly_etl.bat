@echo off
REM ====================================================================
REM  run_nightly_etl.bat - the DAILY data refresh (scheduled at 00:30)
REM   1. run the ETL (reloads the warehouse from the 3 source exports)
REM   2. take a DIFFERENTIAL backup of everything that changed since
REM      the last weekly full backup
REM  If the ETL fails, nothing is loaded (one transaction) and the
REM  backup step is skipped. See output\etl_failure.log.
REM ====================================================================
cd /d "%~dp0"
python etl_script.py >> output\nightly_etl.log 2>&1
if errorlevel 1 (
    echo [%date% %time%] ETL FAILED - see output\etl_failure.log >> output\nightly_etl.log
    exit /b 1
)
python ..\07_Security_Documentation\backup_scripts\backup_restore.py differential >> output\nightly_etl.log 2>&1
echo [%date% %time%] nightly ETL + differential backup finished >> output\nightly_etl.log
