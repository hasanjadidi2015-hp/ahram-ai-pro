# -*- coding: utf-8 -*-
# فقط خواندنی: پوزیشن‌های وبملت که هنوز بسته نشده‌اند (هر position_id یک‌بار با آخرین ردیف)
import sqlite3

conn = sqlite3.connect("file:webmellt.db?mode=ro", uri=True)
rows = conn.execute(
    """
    SELECT s.time, s.signal_type, s.option_symbol, s.option_price, s.stop_loss,
           s.target1, s.outcome, s.outcome_pct, s.position_id
    FROM signal_history s
    JOIN (
        SELECT position_id, MAX(id) AS last_id
        FROM signal_history
        WHERE position_id IS NOT NULL AND signal_type IN ('BUY_CALL', 'BUY_PUT')
        GROUP BY position_id
    ) m ON s.id = m.last_id
    WHERE s.outcome IS NULL OR s.outcome = 'PENDING' OR s.outcome = 'T1_HIT'
    ORDER BY s.time
    """
).fetchall()
conn.close()

print(f"پوزیشن‌های بازِ وبملت: {len(rows)}")
print("زمان آخرین ردیف | نوع | قرارداد | قیمت آخرین ثبت | حد ضرر | هدف۱ | نتیجه | درصد | position_id")
for r in rows:
    print(" | ".join(str(x) for x in r))