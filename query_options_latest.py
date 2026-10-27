# -*- coding: utf-8 -*-
# فقط خواندنی: آخرین ردیف‌های جدول options برای یک قرارداد (پیش‌فرض طملت9041)
import sqlite3
import sys

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "طملت9041"
conn = sqlite3.connect("file:webmellt.db?mode=ro", uri=True)
rows = conn.execute(
    """
    SELECT id, time, symbol, option_price, stock_price
    FROM options
    WHERE symbol = ?
    ORDER BY id DESC
    LIMIT 15
    """,
    (SYMBOL,),
).fetchall()
conn.close()

print(f"آخرین {len(rows)} ردیف options برای {SYMBOL}:")
print("id | زمان | نماد | قیمت اختیار | قیمت سهم")
for r in rows:
    print(" | ".join(str(x) for x in r))
if not rows:
    print("هیچ ردیفی برای این نماد پیدا نشد (این خودش مشکل است)")