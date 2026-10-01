# test_parity.py - verify parity check wiring on real DBs
import sqlite3
from option_selector import get_best_option
DBS = ["ahram_v2.db", "webmellt.db", "shasta.db"]
for db in DBS:
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT last_price FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        px = row[0] if row else 0
    except Exception as e:
        print(db, "PRICE-READ-FAIL", e)
        continue
    print(db, "stock=", px)
    for sig in ("BUY_CALL", "BUY_PUT"):
        try:
            best = get_best_option(db, "X", sig, px)
        except Exception as e:
            print(" ", sig, "EXC", e)
            continue
        if not best:
            print(" ", sig, "NO-CONTRACT")
        else:
            print(" ", sig, best.get("symbol"), "K=", best.get("strike_price_clean"), "P=", best.get("option_price_clean"), "parity_dev_pct=", best.get("parity_dev_pct", "NO-MIRROR"))
print("DONE")