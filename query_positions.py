# -*- coding: utf-8 -*-
# فقط خواندنی: وضعیت پوزیشن‌های باز ربات و آخرین قیمت هر قرارداد (تازه یا قدیمی)
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
        SELECT s.position_id, s.option_symbol, s.option_price, s.stop_loss, s.target1, s.outcome, s.time
        FROM signal_history s
        JOIN (SELECT position_id, MIN(id) AS mid FROM signal_history
              WHERE outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL GROUP BY position_id) m
        ON s.id = m.mid
        ORDER BY s.time
        """
    ).fetchall()
    print(f"=== {name} ({db}) | پوزیشن‌های باز: {len(rows)} ===")
    for pid, sym, entry, sl, t1, outcome, t0 in rows:
        last = conn.execute(
            "SELECT time, option_price, price_fresh FROM options WHERE symbol=? AND option_price>0 ORDER BY id DESC LIMIT 1",
            (sym,),
        ).fetchone()
        if last:
            ltime, lprice, fresh = last
            pct = (lprice / entry - 1) * 100 if entry else 0
            status = "تازه" if fresh == 1 else "قدیمی (خروج پایش نمی‌شود)"
            print(f"{sym} | ورود {entry} (در {t0}) | حد ضرر {sl} | هدف۱ {t1} | وضعیت {outcome}")
            print(f"    آخرین قیمت {lprice} در {ltime} | {pct:+.1f}٪ | {status}")
        else:
            print(f"{sym} | ورود {entry} | قیمتی در options نیست")
    conn.close()