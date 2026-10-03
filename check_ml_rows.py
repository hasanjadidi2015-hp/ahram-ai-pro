# check_ml_rows.py - rows with ML reason in details
import sqlite3
conn = sqlite3.connect("file:ahram_v2.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT time, signal_type, composite_score, option_symbol FROM signal_history WHERE date(time)='2026-10-03' AND details LIKE '%یادگیری%'")
rows = cur.fetchall()
print("ML rows:", len(rows))
for r in rows:
    print("  ", r)
conn.close()
print("DONE")