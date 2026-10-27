# -*- coding: utf-8 -*-
# فقط خواندنی: سیگنال‌های خرید وبملت امروز با وضعیت هر ردیف
import sqlite3
import sys

DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-10-27"
conn = sqlite3.connect("file:webmellt.db?mode=ro", uri=True)
cur = conn.execute(
    """
    SELECT time, signal_type, composite_score, option_symbol, option_price,
           strike_price, stop_loss, target1, outcome, outcome_pct,
           outcome_time, position_id
    FROM signal_history
    WHERE time LIKE ? AND signal_type IN ('BUY_CALL', 'BUY_PUT')
    ORDER BY time
    """,
    (DAY + "%",),
)
rows = cur.fetchall()
conn.close()

print(f"سیگنال‌های خرید {DAY}: {len(rows)} ردیف")
print("زمان | نوع | امتیاز | قرارداد | قیمت ورود | اعمال | حد ضرر | هدف۱ | نتیجه | درصد | زمان نتیجه | position_id")
for r in rows:
    print(" | ".join(str(x) for x in r))