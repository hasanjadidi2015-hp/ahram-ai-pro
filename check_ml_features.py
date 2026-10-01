# check_ml_features.py - which ML features fail in settled rows
import sqlite3, json
conn = sqlite3.connect("file:ahram_v2.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT details, composite_score FROM signal_history WHERE outcome IN ('WIN','LOSS') AND details IS NOT NULL AND details != '' AND id IN (SELECT MIN(id) FROM signal_history WHERE outcome IN ('WIN','LOSS') AND position_id IS NOT NULL GROUP BY position_id)")
rows = cur.fetchall()
conn.close()
print("rows:", len(rows))
bad = {"confidence": 0, "delta": 0, "iv_premium_ratio": 0, "probability_of_profit": 0, "distance_pct": 0, "score": 0}
ok = 0
for details_json, score in rows:
    try:
        d = json.loads(details_json)
    except Exception:
        print("JSON-FAIL")
        continue
    opt = d.get("option") or {}
    tests = [
        ("confidence", opt.get("confidence", 50)),
        ("delta", opt.get("delta", 0.5)),
        ("iv_premium_ratio", opt.get("iv_premium_ratio", 1.0)),
        ("probability_of_profit", opt.get("probability_of_profit", 50)),
        ("distance_pct", opt.get("distance_pct", 0)),
        ("score", score if score is not None else 50),
    ]
    row_ok = True
    for name, v in tests:
        try:
            float(v)
        except Exception:
            bad[name] += 1
            row_ok = False
    if row_ok:
        ok += 1
print("fully-valid rows:", ok)
print("bad counts:", bad)
print("DONE")