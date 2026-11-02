# -*- coding: utf-8 -*-
# فقط خواندنی: نمونه‌ی آخرین ثبت هر قرارداد پرمعامله، برای بررسی تازگی قیمت
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "ahram_v2.db"
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
latest = conn.execute("SELECT MAX(time) FROM options").fetchone()[0]
rows = conn.execute(
    """
    SELECT symbol, option_type, option_price, price_time, price_age_min, price_fresh, volume, trades_count
    FROM options
    WHERE time = ?
    ORDER BY volume DESC
    LIMIT 15
    """,
    (latest,),
).fetchall()
conn.close()

print(f"آخرین ثبت options در {DB}: {latest}")
print("نماد | نوع | قیمت | زمان آخرین معامله | سن (دقیقه) | تازه؟ | حجم | تعداد معاملات")
for r in rows:
    print(" | ".join(str(x) for x in r))