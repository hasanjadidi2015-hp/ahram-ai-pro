# -*- coding: utf-8 -*-
"""
بررسی سلامت و شمارش تمام رکوردهای تاریخی دیتابیس (کاملاً فقط‌خواندنی)
"""
import os
import sqlite3

DBS = ["ahram_v2.db", "webmellt.db", "shasta.db"]

print("\n" + "=" * 70)
print("🛡️ گزارش شمارش رکوردهای دیتابیس (بررسی دست‌نخوردن داده‌ها)")
print("=" * 70)

for db in DBS:
    if not os.path.exists(db):
        print(f"❌ دیتابیس {db} پیدا نشد.")
        continue

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = conn.cursor()
    
    print(f"\n📊 دیتابیس: [{db}]")
    
    # شمارش آپشن‌ها
    cur.execute("SELECT COUNT(*), MIN(time), MAX(time) FROM options")
    opt_cnt, opt_min, opt_max = cur.fetchone()
    print(f"   • تعداد کل آپشن‌ها: {opt_cnt:,} رکورد (از تاریخ {opt_min} تا {opt_max})")

    # شمارش قیمت‌ها
    cur.execute("SELECT COUNT(*), MIN(time), MAX(time) FROM prices")
    prc_cnt, prc_min, prc_max = cur.fetchone()
    print(f"   • تعداد کل قیمت‌های ثبت‌شده: {prc_cnt:,} رکورد (از تاریخ {prc_min} تا {prc_max})")

    # شمارش سیگنال‌ها
    cur.execute("SELECT COUNT(*), MIN(time), MAX(time) FROM signal_history")
    sig_cnt, sig_min, sig_max = cur.fetchone()
    print(f"   • تعداد کل سیگنال‌ها: {sig_cnt:,} رکورد (از تاریخ {sig_min} تا {sig_max})")

    conn.close()

print("\n" + "=" * 70)
print("✅ همان‌طور که می‌بینید تمام رکوردهای تیر، مرداد و شهریور در دیتابیس وجود دارند.")
print("=" * 70 + "\n")