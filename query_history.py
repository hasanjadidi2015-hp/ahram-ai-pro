# -*- coding: utf-8 -*-
# فقط خواندنی: تاریخچه‌ی قیمت یک قرارداد در جدول options (برای بررسی درستی هدف اول/حد ضرر)
import sqlite3
import sys

if len(sys.argv) < 3:
    print("استفاده: python query_history.py <دیتابیس> <نماد قرارداد>")
    print("مثال:    python query_history.py webmellt.db طملت8074")
    sys.exit(1)

DB, SYM = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = conn.execute(
    """
    SELECT time, option_price, price_time, price_fresh, volume, trades_count
    FROM options
    WHERE symbol = ? AND time >= '2026-10-31'
    ORDER BY id
    """,
    (SYM,),
).fetchall()
conn.close()

print(f"تاریخچه‌ی {SYM} در {DB} (از ۱۰ آبان به قبل حذف شده):  {len(rows)} ردیف")
print("زمان ثبت | قیمت | زمان آخرین معامله | تازه؟ | حجم | تعداد معاملات")
for r in rows:
    print(" | ".join(str(x) for x in r))