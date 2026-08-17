# -*- coding: utf-8 -*-
import sqlite3, io, contextlib, os, shutil
import config
from strategy import Strategy

REAL_DB = config.DATABASE_NAME
TEMP_DB = "_bt.db"
FORWARD_DAYS = 5

conn = sqlite3.connect(REAL_DB)
rows = conn.execute("SELECT time, last_price, volume FROM prices WHERE last_price > 0 ORDER BY id").fetchall()
conn.close()

days = {}
for t, p, v in rows:
    d = str(t)[:10]
    if d:
        days[d] = (float(p), float(v or 0))
daily = [(d, days[d][0], days[d][1]) for d in sorted(days)]
print("Daily points:", len(daily))
if len(daily) < 40:
    print("Not enough data")
    raise SystemExit

if os.path.exists(TEMP_DB):
    os.remove(TEMP_DB)
shutil.copy(REAL_DB, TEMP_DB)
conn = sqlite3.connect(TEMP_DB)
conn.execute("DELETE FROM prices")
config.DATABASE_NAME = TEMP_DB

WARMUP = 30
for i in range(WARMUP):
    d, p, v = daily[i]
    conn.execute("INSERT INTO prices (time, last_price, closing_price, volume) VALUES (?,?,?,?)", (d, p, p, v))
conn.commit()

buys = []
for i in range(WARMUP, len(daily)):
    d, p, v = daily[i]
    conn.execute("INSERT INTO prices (time, last_price, closing_price, volume) VALUES (?,?,?,?)", (d, p, p, v))
    conn.commit()
    strat = Strategy()
    strat._in_quiet_period = lambda: False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = strat.analyze()
    except Exception:
        res = None
    try:
        strat.close()
    except Exception:
        pass
    action = res[0] if res else "WATCH"
    if action in ("BUY", "STRONG BUY"):
        fwd_idx = min(i + FORWARD_DAYS, len(daily) - 1)
        fwd = daily[fwd_idx][1]
        ret = round((fwd / p - 1) * 100, 1)
        buys.append({"day": d, "price": p, "fwd": fwd, "ret": ret})

conn.close()
try:
    os.remove(TEMP_DB)
except Exception:
    pass

print("\n" + "=" * 50)
print("BACKTEST (%d BUY signals, %d-day forward)" % (len(buys), FORWARD_DAYS))
print("=" * 50)
if not buys:
    print("No BUY signals in history.")
else:
    wins = [b for b in buys if b["ret"] > 0]
    losses = [b for b in buys if b["ret"] <= 0]
    wr = round(len(wins) / len(buys) * 100, 1)
    avg_w = round(sum(b["ret"] for b in wins) / len(wins), 1) if wins else 0
    avg_l = round(sum(b["ret"] for b in losses) / len(losses), 1) if losses else 0
    print("Win rate: %d/%d = %s%%" % (len(wins), len(buys), wr))
    print("Avg gain: +%s%% | Avg loss: %s%%" % (avg_w, avg_l))
    print("\nFirst 10 signals:")
    for b in buys[:10]:
        print("  %s | %s -> %s | %s%%" % (b["day"], int(b["price"]), int(b["fwd"]), b["ret"]))