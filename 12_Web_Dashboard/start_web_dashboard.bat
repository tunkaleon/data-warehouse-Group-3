@echo off
REM =====================================================================
REM  start_web_dashboard.bat - double-click to start the web dashboards
REM  1. installs Flask if it is missing   2. starts the web server
REM  3. opens http://127.0.0.1:5000 in the browser
REM  Close this window (or press Ctrl+C) to stop the server.
REM =====================================================================
cd /d "%~dp0"
python -c "import flask" 2>NUL || python -m pip install -r requirements.txt
start "" http://127.0.0.1:5000
python app.py
pause
