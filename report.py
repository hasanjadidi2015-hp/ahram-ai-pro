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
    except Exception as e:
        print(f"  {name}: خطا - {e}")

# سیگنال‌ها
print(f"\n📋 سیگنال‌های امروز ({today}):")
total = 0
signal_counts = {}   # name -> تعداد سیگنال امروز
last_update = {}     # name -> آخرین زمان ثبت‌شده امروز
for name, db in DBS:
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute(
            "SELECT time, signal_type, composite_score FROM signal_history "
            "WHERE time LIKE ? ORDER BY id DESC",
            (f"{today}%",),
        )
        rows = cur.fetchall()
        signal_counts[name] = len(rows)
        if rows:
            last_update[name] = rows[0][0]
            for r in rows:
                sig = {"BUY_CALL": "🟢 خرید کال", "BUY_PUT": "🔴 خرید پوت", "WATCH": "🟡 تحت نظر"}.get(r[1], r[1])
                print(f"  {name} | {r[0]} | {sig} | امتیاز: {r[2]}")
                total += 1
        else:
            last_update[name] = None
            print(f"  {name}: بدون سیگنال")
        conn.close()
    except Exception as e:
        signal_counts[name] = 0
        last_update[name] = None
        print(f"  {name}: خطا - {e}")

print(f"\n📊 کل سیگنال‌های امروز: {total}")

# پوزیشن‌های باز (برای گزارش آخر روز خیلی مهمه که چی هنوز بازه)
# نکته: یه ردیف در ازای هر option_symbol یکتا (نه هر بار که سیگنال تکرار
# شده)، وگرنه یه معامله‌ی واحد ده‌ها بار جداگانه لیست می‌شه.
print("\n📌 پوزیشن‌های باز در پایان امروز:")
open_count = 0
for name, db in DBS:
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute(
            "SELECT option_symbol, option_price, stop_loss, target1, target2, outcome, MIN(id) "
            "FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') "
            "AND position_id IS NOT NULL GROUP BY position_id"
        )
        rows = cur.fetchall()
        for sym, entry, sl, t1, t2, outcome, _min_id in rows:
            cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (sym,))
            pr = cur.fetchone()
            entry_f = float(entry) if entry else 0
            cur_f = float(pr[0]) if pr and pr[0] else entry_f
            pct = round(((cur_f - entry_f) / entry_f) * 100, 1) if entry_f else 0
            status = "نیم‌فروخته شده" if outcome == "T1_HIT" else "باز"
            print(f"  {name} | {sym} | ورود {entry_f:,.0f} -> فعلی {cur_f:,.0f} ({pct:+}%) | {status}")
            open_count += 1
        conn.close()
    except Exception as e:
        print(f"  {name}: خطا - {e}")
if open_count == 0:
    print("  هیچ پوزیشن بازی نمونده.")

# بررسی سلامت سیستم — تلاش برای پیدا کردن باگ/قطعی احتمالی
print("\n🔍 بررسی سلامت (پیدا کردن مشکل احتمالی):")
issues_found = 0
MARKET_CLOSE = "12:30"
STALE_TOLERANCE_MIN = 12  # کمتر از این فاصله تا پایان بازار طبیعیه (فاصله‌ی سیکل‌ها ۵ دقیقه‌ست)
for name, _db in DBS:
    if signal_counts.get(name, 0) == 0:
        print(f"  ⚠️ {name}: امروز هیچ سیگنالی ثبت نشده — احتمال قطعی در جمع‌آوری داده یا خطای تحلیل")
        issues_found += 1
    else:
        last_t = last_update.get(name)
        if last_t:
            last_hm = last_t.split(" ")[1][:5] if " " in last_t else None
            if last_hm:
                mc_h, mc_m = map(int, MARKET_CLOSE.split(":"))
                lh, lm = map(int, last_hm.split(":"))
                gap_min = (mc_h * 60 + mc_m) - (lh * 60 + lm)
                if gap_min > STALE_TOLERANCE_MIN:
                    print(f"  ⚠️ {name}: آخرین سیگنال ساعت {last_hm} ثبت شده ({gap_min} دقیقه قبل از پایان بازار {MARKET_CLOSE}) — احتمال توقف زودهنگام ربات")
                    issues_found += 1
if issues_found == 0:
    print("  ✅ چیز مشکوکی پیدا نشد.")

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