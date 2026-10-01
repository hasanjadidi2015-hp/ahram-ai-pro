# check_ml_live.py - model verdict on tonight's real ahram rows
import sqlite3, json
from ml_adjust import get_ml_adjustment
conn = sqlite3.connect("file:ahram_v2.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT time, signal_type, composite_score, details FROM signal_history ORDER BY id DESC LIMIT 3")
rows = cur.fetchall()
conn.close()
for t, st, score, details in rows:
    try:
        d = json.loads(details)
    except Exception:
        print(t, st, "JSON-FAIL")
        continue
    opt = d.get("option") or {}
    print(t, st, "score=", score, "opt=", opt.get("symbol"))
    if opt:
        print("  ml:", get_ml_adjustment(opt, score, "ahram_v2.db"))
    else:
        print("  ml: SKIPPED (no option, live skips too)")
print("DONE")