# -*- coding: utf-8 -*-
import sqlite3
for db in ["ahram_v2.db", "webmellt.db", "shasta.db"]:
    print("=" * 50)
    print("DB:", db)
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    cur = con.cursor()
    cur.execute("SELECT MAX(time) FROM options")
    print("latest snapshot:", cur.fetchone()[0])
    cur.execute("SELECT position_id FROM signal_history WHERE position_id IS NOT NULL GROUP BY position_id")
    pids = [r[0] for r in cur.fetchall()]
    n_open = 0
    for pid in pids:
        cur.execute("SELECT outcome FROM signal_history WHERE position_id=? ORDER BY id DESC LIMIT 1", (pid,))
        if cur.fetchone()[0] not in ("PENDING", "T1_HIT"):
            continue
        n_open += 1
        cur.execute("SELECT option_symbol, option_price FROM signal_history WHERE position_id=? ORDER BY id ASC LIMIT 1", (pid,))
        sym, entry = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM options WHERE symbol=?", (sym,))
        cnt = cur.fetchone()[0]
        cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (sym,))
        r = cur.fetchone()
        print("pos:", pid, "| entry:", entry, "| opt_rows:", cnt, "| latest:", r[0] if r else "NONE")
        if cnt == 0 and sym:
            cur.execute("SELECT DISTINCT symbol FROM options WHERE symbol LIKE ?", ("%" + str(sym).strip() + "%",))
            print("   near:", [x[0] for x in cur.fetchall()][:5])
    print("open positions:", n_open)
    con.close()
print("DONE")