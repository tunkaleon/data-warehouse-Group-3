"""
=====================================================================
 run_all.py  -  rebuild the WHOLE project from scratch, in order
=====================================================================
   1. generate the 3 messy source files      09_Source_Data
   2. create the SQLite database (01-07)      03_Database_Files/library_dw.db
   3. run the ETL (clean + load)              04_ETL_Files
   4. create the users (hashed passwords)     07_Security_Documentation/security_tools
   5. run the 31 business queries -> Excel    05_Analytics_Package
   6. bonus analytics (correlation, forecast, anomalies)
   7. draw the dashboard images               06_Dashboards
   8. security tests -> security_test_results.txt
   9. full backup + restore test -> backup_test_results.txt

 HOW TO RUN (from this folder):   python run_all.py
 Needs: pip install pandas openpyxl matplotlib   (cryptography is optional)
=====================================================================
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEC = ROOT / "07_Security_Documentation"

STEPS = [
    ("Generate source data",        "09_Source_Data",              ["generate_source_data.py"], None),
    ("Build SQLite database",       "03_Database_Files",           ["build_database.py"], None),
    ("ETL: extract-transform-load", "04_ETL_Files",                ["etl_script.py"], None),
    ("Create users",                "07_Security_Documentation/security_tools", ["secure_access.py", "--setup"], None),
    ("Business queries -> Excel",   "05_Analytics_Package",        ["run_business_queries.py"], None),
    ("Bonus analytics",             "05_Analytics_Package",        ["advanced_analytics.py"], None),
    ("Dashboard images",            "06_Dashboards",               ["build_dashboard_images.py"], None),
    ("Security tests",              "07_Security_Documentation/security_tools", ["secure_access.py", "--demo"],
     SEC / "security_tools" / "security_test_results.txt"),
    ("Full backup",                 "07_Security_Documentation/backup_scripts", ["backup_restore.py", "full"], None),
    ("Restore test",                "07_Security_Documentation/backup_scripts", ["backup_restore.py", "verify"],
     SEC / "backup_scripts" / "backup_test_results.txt"),
]

if __name__ == "__main__":
    start = time.time()
    for number, (title, folder, args, save_to) in enumerate(STEPS, 1):
        print(f"\n[{number}/{len(STEPS)}] {title}")
        result = subprocess.run([sys.executable] + args, cwd=ROOT / folder, capture_output=True, text=True)
        output = result.stdout + result.stderr
        if save_to:
            save_to.write_text(output, encoding="utf-8")
            print(f"   output saved in {save_to.relative_to(ROOT)}")
        last_lines = [line for line in output.strip().splitlines() if "findfont" not in line][-2:]
        for line in last_lines:
            print("   " + line)
        if result.returncode != 0:
            sys.exit(f"\nSTOPPED: step '{title}' failed (see the message above).")
    print(f"\nAll {len(STEPS)} steps finished in {time.time() - start:.0f} s.")
