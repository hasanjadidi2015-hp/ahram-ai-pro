# -*- coding: utf-8 -*-
import sys
import sqlite3
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except:
    pass

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
today = datetime.now().strftime("%Y-%m-%d")

print("=" * 60)
print(f"📊 گزارش AHRAM AI - {today}")
print("=" * 60)

# قیمت‌ها
print("\n💰 قیمت‌های فعلی:")
for name, db in DBS:
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT last_price FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        price = f"{int(float(r[0])):,}" if r else "-"
        print(f"  {name}: {price} ریال")
        conn.close()
    except:
        print(f"  {name}: خطا")

# سیگنال‌ها
print(f"\n📋 سیگنال‌های امروز ({today}):")
total = 0
for name, db in DBS:
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT time, signal_type, composite_score FROM signal_history WHERE time LIKE ? ORDER BY id DESC", (f"{today}%",))
        rows = cur.fetchall()
        if rows:
            for r in rows:
                sig = {"BUY_CALL": "🟢 خرید کال", "BUY_PUT": "🔴 خرید پوت", "WATCH": "🟡 تحت نظر"}.get(r[1], r[1])
                print(f"  {name} | {r[0]} | {sig} | امتیاز: {r[2]}")
                total += 1
        else:
            print(f"  {name}: بدون سیگنال")
        conn.close()
    except:
        print(f"  {name}: خطا")

print(f"\n📊 کل سیگنال‌های امروز: {total}")

# داشبورد
print("\n🔄 بروزرسانی داشبورد...")
try:
    import dashboard
    dashboard.generate()
    print("  ✅ داشبورد بروزرسانی شد")
except Exception as e:
    print(f"  ❌ خطا: {e}")

print("\n" + "=" * 60)
print("✅ پایان گزارش")
print("=" * 60)