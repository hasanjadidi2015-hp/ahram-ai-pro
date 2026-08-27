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
all_times = {}        # name -> لیست همه‌ی زمان‌های امروز (برای تشخیص شکاف وسط روز)
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
        all_times[name] = [r[0] for r in rows]
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
        all_times[name] = []
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

# معامله‌های تسویه‌شده‌ی امروز (WIN/LOSS) -- بدون این بخش، «چرا فلان نماد
# که کلی سیگنال گرفته بود پوزیشن بازش صفره» بی‌جواب می‌مونه: یا واقعاً
# طی روز به هدف رسیده (WIN)، یا مشکوکه و باید بررسی بشه.
print("\n📈 معامله‌های تسویه‌شده‌ی امروز:")
resolved_count = 0
wins_today = losses_today = 0
for name, db in DBS:
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute(
            "SELECT option_symbol, option_price, outcome, outcome_pct, MAX(time) "
            "FROM signal_history WHERE outcome IN ('WIN','LOSS') AND position_id IS NOT NULL "
            "AND time LIKE ? GROUP BY position_id ORDER BY MAX(time)",
            (f"{today}%",),
        )
        rows = cur.fetchall()
        for sym, entry, outcome, pct, last_time in rows:
            icon = "✅" if outcome == "WIN" else "❌"
            print(f"  {name} | {sym} | {icon} {outcome} ({pct:+}%) | تسویه: {last_time}")
            resolved_count += 1
            if outcome == "WIN":
                wins_today += 1
            else:
                losses_today += 1
        conn.close()
    except Exception as e:
        print(f"  {name}: خطا - {e}")
if resolved_count == 0:
    print("  امروز معامله‌ای تسویه نشده.")
else:
    print(f"  جمع: {wins_today} برد / {losses_today} باخت")

# بررسی سلامت سیستم — تلاش برای پیدا کردن باگ/قطعی احتمالی
print("\n🔍 بررسی سلامت (پیدا کردن مشکل احتمالی):")
issues_found = 0
MARKET_CLOSE = "12:30"
STALE_TOLERANCE_MIN = 12  # کمتر از این فاصله تا پایان بازار طبیعیه (فاصله‌ی سیکل‌ها ۵ دقیقه‌ست)
GAP_TOLERANCE_MIN = 15    # شکاف بیشتر از این بین دو سیگنال پشت‌سرهم مشکوکه
for name, _db in DBS:
    if signal_counts.get(name, 0) == 0:
        print(f"  ⚠️ {name}: امروز هیچ سیگنالی ثبت نشده — احتمال قطعی در جمع‌آوری داده یا خطای تحلیل")
        issues_found += 1
        continue

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

    # شکاف وسط روز -- قبلاً این چک وجود نداشت و یه توقف ۹۰ دقیقه‌ای رو
    # ندیده گرفته بود چون فقط آخرین سیگنال روز رو چک می‌کرد، نه فاصله‌ی
    # بین سیگنال‌های پشت‌سرهم.
    times_today = sorted(all_times.get(name, []))
    for i in range(1, len(times_today)):
        try:
            t1 = datetime.strptime(times_today[i-1].split(" ")[1], "%H:%M:%S")
            t2 = datetime.strptime(times_today[i].split(" ")[1], "%H:%M:%S")
            gap = (t2 - t1).total_seconds() / 60
            if gap > GAP_TOLERANCE_MIN:
                print(f"  ⚠️ {name}: شکاف {gap:.0f} دقیقه‌ای بین {times_today[i-1][11:16]} و {times_today[i][11:16]} — ربات توی این بازه سیگنالی ثبت نکرده")
                issues_found += 1
        except Exception:
            continue

if issues_found == 0:
    print("  ✅ چیز مشکوکی پیدا نشد.")

# تأثیر خبرها روی قیمت (کدال + ناظر بازار) -- برای تصمیم‌گیری آینده که
# آیا به‌عنوان سیگنال کمکی ازشون استفاده کنیم یا نه
print("\n📰 تأثیر خبرها روی قیمت (در حال جمع‌آوری):")
try:
    from news_impact import update_news_impact, news_impact_summary, MIN_SAMPLES as _NEWS_MIN
    any_summary = False
    for name, db in DBS:
        try:
            update_news_impact(db)
            summary = news_impact_summary(db)
            for (source, category), s in summary.items():
                any_summary = True
                label = {"codal": "کدال", "supervisor": "ناظر بازار"}.get(source, source)
                ready_txt = "✅ آماده برای تصمیم" if s["ready"] else f"⏳ {s['samples']}/{_NEWS_MIN} نمونه"
                print(f"  {name} | {label}/{category} | {ready_txt} | تأثیر ۱روزه:{s['avg_impact_1d']}% "
                      f"۵روزه:{s['avg_impact_5d']}% ۲۰روزه:{s['avg_impact_20d']}%")
        except Exception as e:
            print(f"  {name}: خطا - {e}")
    if not any_summary:
        print("  هنوز هیچ خبری کامل ارزیابی نشده (نیاز به گذشت ۲۰ روز کاری از تاریخ هر خبر).")
except Exception as e:
    print(f"  خطا در ماژول تأثیر اخبار: {e}")

# داشبورد
print("\n🔄 بروزرسانی داشبورد...")
try:
    import dashboard
    dashboard.generate()
    print("  ✅ داشبورد بروزرسانی شد")
except Exception as e:
    print(f"  ❌ خطا: {e}")

# زنجیره قرارداد - خودکار روزانه (فقط خواندنی، بدون اثر بر سیگنال)
# چون داده‌اش از خود TSETMC میاد و تمیزه، هر روز خودکار اجرا میشه
# این بخش بعد از 10 روز کاری برای اتصالات اصلی استفاده میشه، الان فقط جمع‌آوری
print("\n🔗 بروزرسانی زنجیره قرارداد (خودکار روزانه - فقط خواندنی)...")
try:
    import strategy_bridge
    # strategy_bridge.main() از argparse استفاده می‌کنه، برای اینکه با آرگومان‌های report تداخل نکنه، sys.argv رو موقتا پاک می‌کنیم
    import sys
    old_argv = sys.argv
    sys.argv = [old_argv[0]]
    try:
        strategy_bridge.main()
        print("  ✅ پل استراتژی (ahram_strategy_data.json) بروز شد")
    finally:
        sys.argv = old_argv
except Exception as e:
    print(f"  ⚠️ خطا پل استراتژی: {e}")

try:
    import shadow_strategy
    import sys
    old_argv = sys.argv
    sys.argv = [old_argv[0]]
    try:
        shadow_strategy.main()
        print("  ✅ گزارش Shadow (ahram_shadow_report.json) بروز شد")
    finally:
        sys.argv = old_argv
except Exception as e:
    print(f"  ⚠️ خطا Shadow: {e}")

try:
    import connect_strategy_dashboard
    import sys
    old_argv = sys.argv
    sys.argv = [old_argv[0]]
    try:
        connect_strategy_dashboard.main()
        print("  ✅ داشبورد LIVE4 بروز شد")
    finally:
        sys.argv = old_argv
except Exception as e:
    print(f"  ⚠️ خطا اتصال داشبورد VIP: {e}")

# Max Pain - خودکار روزانه (فقط محاسبه و ذخیره، بدون اثر بر سیگنال)
print("\n📍 بروزرسانی Max Pain (خودکار روزانه - فقط ذخیره)...")
try:
    import max_pain
    for _name, _db in DBS:
        try:
            results = max_pain.analyze_database(_db, save=True)
            if results:
                print(f"  ✅ Max Pain {_name}: {len(results)} سررسید محاسبه شد")
            else:
                print(f"  ⚠️ Max Pain {_name}: داده‌ای نبود")
        except Exception as e:
            print(f"  ⚠️ Max Pain {_name} خطا: {e}")
except Exception as e:
    print(f"  ⚠️ خطا کلی Max Pain: {e}")

print("\n" + "=" * 60)
print("✅ پایان گزارش")
print("=" * 60)