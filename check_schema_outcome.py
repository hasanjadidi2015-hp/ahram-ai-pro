# check_schema_outcome.py - outcome default + NULL counts per DB
import sqlite3
for db in ["ahram_v2.db", "webmellt.db", "shasta.db"]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(signal_history)")
    for cid, name, ctype, notnull, dflt, pk in cur.fetchall():
        if name == "outcome":
            print(db, "| outcome type:", ctype, "| default:", dflt)
    cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome IS NULL")
    print("  NULL-outcome rows:", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM signal_history")
    print("  total rows:", cur.fetchone()[0])
    conn.close()
print("DONE")