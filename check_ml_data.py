# check_ml_data.py - ML readiness: samples per DB + sklearn
import sqlite3, json
try:
    import sklearn
    print("sklearn:", sklearn.__version__)
except Exception as e:
    print("sklearn: MISSING", e)
DBS = ["ahram_v2.db", "webmellt.db", "shasta.db"]
for db in DBS:
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT position_id) FROM signal_history WHERE outcome='WIN'")
        w = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT position_id) FROM signal_history WHERE outcome='LOSS'")
        l = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome IN ('WIN','LOSS') AND details IS NOT NULL AND details != '' AND id IN (SELECT MIN(id) FROM signal_history WHERE outcome IN ('WIN','LOSS') AND position_id IS NOT NULL GROUP BY position_id)")
        elig = cur.fetchone()[0]
        cur.execute("SELECT details FROM signal_history WHERE outcome IN ('WIN','LOSS') AND details IS NOT NULL AND details != '' LIMIT 1")
        r = cur.fetchone()
        conn.close()
        print(db, "WINpos=", w, "LOSSpos=", l, "train_eligible=", elig, "(need 15)")
        if r:
            try:
                d = json.loads(r[0])
                opt = d.get("option") or {}
                print("  sample option keys:", sorted(opt.keys()))
            except Exception as e:
                print("  details parse FAIL:", e)
        else:
            print("  no details rows")
    except Exception as e:
        print(db, "DB-FAIL", e)
print("DONE")