# check_ml_daily.py - ML reason rows for a date (default today)
import sqlite3, sys
from datetime import datetime
day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
for db in ["ahram_v2.db", "webmellt.db", "shasta.db"]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("SELECT time, signal_type, composite_score FROM signal_history WHERE date(time)=? AND details LIKE '%یادگیری%'", (day,)).fetchall()
    conn.close()
    print(db, day, "ML rows:", len(rows))
    for r in rows:
        print("  ", r)
print("DONE")