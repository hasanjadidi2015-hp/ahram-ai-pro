# backfill_outcome.py - ONE-TIME: Sat BUY NULL->PENDING, old BUY NULL->INCONCLUSIVE
import sqlite3
for db in ["webmellt.db", "shasta.db"]:
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("UPDATE signal_history SET outcome='PENDING' WHERE outcome IS NULL AND signal_type IN ('BUY_CALL','BUY_PUT') AND stop_loss IS NOT NULL AND target1 IS NOT NULL AND date(time)='2026-10-03'")
    p = cur.rowcount
    cur.execute("UPDATE signal_history SET outcome='INCONCLUSIVE' WHERE outcome IS NULL AND signal_type IN ('BUY_CALL','BUY_PUT')")
    i = cur.rowcount
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome IS NULL AND signal_type IN ('BUY_CALL','BUY_PUT')")
    left = cur.fetchone()[0]
    conn.close()
    print(db, "sat->PENDING:", p, "| old->INCONCLUSIVE:", i, "| BUY still NULL:", left)
print("DONE")