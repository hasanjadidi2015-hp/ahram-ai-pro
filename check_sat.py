# check_sat.py - Sat review: w/sh positions + ahram 09:07 ML reason
import sqlite3, json
for db in ["webmellt.db", "shasta.db"]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute("SELECT time, signal_type, composite_score, option_symbol, position_id, outcome FROM signal_history WHERE date(time)='2026-10-03' AND signal_type IN ('BUY_CALL','BUY_PUT') ORDER BY id")
    rows = cur.fetchall()
    print(db, "BUY rows today:", len(rows))
    for r in rows[:6]:
        print("  ", r)
    if len(rows) > 6:
        print("  ... +", len(rows)-6, "more")
    cur.execute("SELECT COUNT(DISTINCT position_id) FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL")
    print("  open positions now:", cur.fetchone()[0])
    conn.close()
conn = sqlite3.connect("file:ahram_v2.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT time, signal_type, composite_score, details FROM signal_history WHERE time LIKE '2026-10-03 09:07%'")
for t, st, sc, det in cur.fetchall():
    d = json.loads(det)
    print("ahram", t, st, sc)
    print("  reasons:", d.get("reasons"))
conn.close()
print("DONE")