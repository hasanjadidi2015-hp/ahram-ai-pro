# -*- coding: utf-8 -*-
# فقط خواندنی: ردیف‌های قیمت آپشن طهرم9028 در ۱۸ اکتبر ۰۹:۲۰ تا ۰۹:۵۰
import sqlite3

conn = sqlite3.connect("file:ahram_v2.db?mode=ro", uri=True)
cur = conn.cursor()
rows = cur.execute(
    """
    SELECT time, symbol, option_price, stock_price
    FROM options
    WHERE symbol LIKE '%9028%'
      AND time BETWEEN '2026-10-18 09:20' AND '2026-10-18 09:50'
    ORDER BY time
    """
).fetchall()
conn.close()

print(f"تعداد ردیف: {len(rows)}")
for r in rows:
    print(r)