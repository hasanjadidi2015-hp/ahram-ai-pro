# -*- coding: utf-8 -*-
"""
تشخیص دقیق چرا خبرهای بک‌لاگ کامل ارزیابی نمی‌شن -- فقط خواندنی، هیچ‌چیزی
رو تغییر نمی‌ده (بر خلاف news_impact.py که واقعاً UPDATE می‌زنه).

برای چند تا نمونه از خبرهای گیرکرده، دقیق نشون می‌ده:
- event_date واقعیش چیه
- چند تا "روز کاری" بعدش تو جدول prices پیدا شده
- آیا قیمت روز بیستم (یا بعدش) واقعاً موجوده یا نه

اجرا:
    python diagnose_news_stuck.py اهرم
    python diagnose_news_stuck.py وبملت
    python diagنose_news_stuck.py شستا
"""
import sqlite3
import sys

SYMBOL_DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db",
}


def diagnose(name, db_path, sample_size=8):
    print(f"\n{'=' * 70}")
    print(f"🔎 تشخیص بک‌لاگ خبر {name}")
    print(f"{'=' * 70}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, time, event_date, price_at_news, source, category "
        "FROM daily_news WHERE fully_evaluated=0 AND price_at_news IS NOT NULL "
        "ORDER BY id ASC LIMIT ?",
        (sample_size,),
    )
    rows = cur.fetchall()

    if not rows:
        print("   هیچ ردیف ارزیابی‌نشده‌ای پیدا نشد.")
        conn.close()
        return

    for news_id, news_time, event_date, price_at_news, source, category in rows:
        ref_date = (event_date or news_time).split(" ")[0]
        print(f"\n   --- خبر id={news_id} ({source}/{category}) ---")
        print(f"      time (زمان کشف)  : {news_time}")
        print(f"      event_date (رخداد): {event_date}")
        print(f"      ref_date استفاده‌شده: {ref_date}")

        cur.execute(
            "SELECT DISTINCT date(time) as d FROM prices WHERE date(time) >= ? ORDER BY d",
            (ref_date,),
        )
        trading_dates = [r[0] for r in cur.fetchall() if r[0]]
        print(f"      تعداد روز کاری پیدا‌شده بعد از ref_date: {len(trading_dates)}")

        if len(trading_dates) == 0:
            print("      ⚠️ هیچ روز کاری‌ای پیدا نشد -- یعنی date(time)>=ref_date تو prices هیچ رکوردی نداره")
            print(f"         (احتمال: فرمت ref_date با فرمت ستون time جدول prices جور درنمیاد)")
        elif len(trading_dates) < 21:
            print(f"      ℹ️ هنوز به ۲۱ روز کاری نرسیده (فقط {len(trading_dates)} تا) -- طبیعیه، صبر لازمه")
        else:
            found_price = False
            for idx in range(20, min(len(trading_dates), 25)):
                cur.execute(
                    "SELECT last_price FROM prices WHERE date(time)=? AND last_price IS NOT NULL "
                    "AND last_price>0 ORDER BY id DESC LIMIT 1",
                    (trading_dates[idx],),
                )
                r = cur.fetchone()
                status = f"قیمت={r[0]}" if (r and r[0]) else "قیمت پیدا نشد"
                print(f"         روز شماره {idx+1} ({trading_dates[idx]}): {status}")
                if r and r[0]:
                    found_price = True
                    break
            if found_price:
                print("      ✅ باید کامل ارزیابی بشه -- اگه نشده، مشکل جای دیگه‌ایه (مثلاً commit)")
            else:
                print("      ⚠️ حتی تا روز ۲۵ ام هم قیمت پیدا نشد -- گپ داده‌ی واقعی")

    conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    targets = {args[0]: SYMBOL_DBS[args[0]]} if args and args[0] in SYMBOL_DBS else SYMBOL_DBS
    for name, db in targets.items():
        diagnose(name, db)