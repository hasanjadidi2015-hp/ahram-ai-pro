# check_train_rows.py - dates and richness of ML training rows
import sqlite3, json
conn = sqlite3.connect("file:ahram_v2.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT time, signal_type, composite_score, outcome, details FROM signal_history WHERE outcome IN ('WIN','LOSS') AND details IS NOT NULL AND details != '' AND id IN (SELECT MIN(id) FROM signal_history WHERE outcome IN ('WIN','LOSS') AND position_id IS NOT NULL GROUP BY position_id) ORDER BY time")
rows = cur.fetchall()
print("train rows:", len(rows))
for t, st, sc, oc, det in rows:
    try:
        opt = (json.loads(det).get("option") or {})
        has = "RICH" if "probability_of_profit" in opt else "raw"
        print(t, st, sc, oc, "optkeys=", len(opt), has)
    except Exception:
        print(t, st, sc, oc, "JSON-FAIL")
cur.execute("SELECT time, signal_type, details FROM signal_history WHERE date(time)='2026-10-03' AND signal_type IN ('BUY_CALL','BUY_PUT') LIMIT 3")
print("oct3 rows:")
for t, st, det in cur.fetchall():
    try:
        opt = (json.loads(det).get("option") or {})
        has = "RICH" if "probability_of_profit" in opt else "raw"
        print(t, st, "optkeys=", len(opt), has)
    except Exception:
        print(t, st, "JSON-FAIL")
conn.close()
print("DONE")