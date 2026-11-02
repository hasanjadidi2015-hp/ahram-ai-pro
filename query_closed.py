# -*- coding: utf-8 -*-
# فقط خواندنی: پوزیشن‌های بسته‌شده (WIN / LOSS / BREAK_EVEN / NO_TRADE) با زمان و قیمت خروج
import os
import sqlite3

DBS = [("وبملت", "webmellt.db"), ("اهرم", "ahram_v2.db"), ("شستا", "shasta.db")]
for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(
        """
        SELECT s.position_id, s.option_symbol, s.option_price, s.outcome, s.outcome_pct, s.outcome_time
        FROM signal_history s
        JOIN (SELECT position_id, MAX(id) AS mid FROM signal_history
              WHERE outcome IN ('WIN','LOSS','BREAK_EVEN','NO_TRADE','T1_HIT') AND position_id IS NOT NULL
              GROUP BY position_id) m ON s.id = m.mid
        WHERE s.outcome <> 'T1_HIT'
        ORDER BY s.outcome_time
        """
    ).fetchall()
    print(f"=== {name} ({db}) | بسته‌شده: {len(rows)} ===")
    for pid, sym, entry, outcome, pct, t_out in rows:
        last = conn.execute(
            "SELECT time, option_price, price_fresh, volume FROM options "
            "WHERE symbol=? AND time<=? ORDER BY id DESC LIMIT 1",
            (sym, t_out or "9999"),
        ).fetchone()
        ltxt = f"آخرین قیمت ثبت‌شده قبل از خروج: {last[1]} در {last[0]} (تازه={last[2]}، حجم={last[3]})" if last else "قیمتی قبل از خروج نیست"
        print(f"{sym} | ورود {entry} | نتیجه {outcome} | درصد {pct} | زمان خروج {t_out}")
        print(f"    {ltxt}")
    conn.close()