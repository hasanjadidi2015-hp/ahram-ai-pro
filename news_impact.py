# -*- coding: utf-8 -*-
"""
ارزیابی تأثیر واقعی خبر روی قیمت -- ۱، ۵، و ۲۰ روز کاری بعد از هر خبر.

روش: «روز کاری» یعنی یه روز که ربات واقعاً داده جمع کرده (یه تاریخ متمایز
توی جدول prices) -- نه محاسبه‌ی تقویمی، چون همینه که با ساعات واقعی بازار
هماهنگه (تعطیلات/جمعه‌ها خودشون حذف می‌شن، چون داده‌ای براشون ثبت نمی‌شه).

بعد از رسیدن به ۲۰ روز کاری از تاریخ خبر، اون خبر «کامل ارزیابی‌شده»
علامت می‌خوره و دیگه دوباره پردازش نمی‌شه.

⚠️ خروجی این ماژول فقط برای مشاهده و تصمیم‌گیریه -- خودش هیچ اثری روی
امتیاز/سیگنال نداره. فقط وقتی نمونه‌ی کافی (حداقل MIN_SAMPLES خبر کامل
ارزیابی‌شده) جمع بشه، summary قابل‌اعتماد می‌شه.
"""
import sqlite3
from datetime import datetime

import config

MIN_SAMPLES = 15


def _trading_dates_on_or_after(cur, start_date):
    cur.execute(
        "SELECT DISTINCT date(time) as d FROM prices WHERE date(time) >= ? ORDER BY d",
        (start_date,),
    )
    return [r[0] for r in cur.fetchall() if r[0]]


def _price_on_date(cur, date_str):
    cur.execute(
        "SELECT last_price FROM prices WHERE date(time)=? AND last_price IS NOT NULL "
        "AND last_price>0 ORDER BY id DESC LIMIT 1",
        (date_str,),
    )
    r = cur.fetchone()
    return float(r[0]) if r and r[0] else None


def update_news_impact(db_path=None):
    """برای هر خبری که هنوز کامل ارزیابی نشده، چک می‌کنه چند روز کاری از
    تاریخش گذشته و outcome_pct_1d/5d/20d رو (اگه ممکن بود) پر می‌کنه."""
    db_path = db_path or config.DATABASE_NAME
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, time, price_at_news, outcome_pct_1d, outcome_pct_5d, outcome_pct_20d "
        "FROM daily_news WHERE fully_evaluated=0 AND price_at_news IS NOT NULL"
    )
    rows = cur.fetchall()

    updated = 0
    for news_id, news_time, price_at_news, o1, o5, o20 in rows:
        news_date = news_time.split(" ")[0]
        trading_dates = _trading_dates_on_or_after(cur, news_date)
        if not trading_dates:
            continue

        changed = False
        updates = {}

        if o1 is None and len(trading_dates) >= 2:
            p1 = _price_on_date(cur, trading_dates[1])
            if p1:
                updates["outcome_pct_1d"] = round((p1 - price_at_news) / price_at_news * 100, 2)
                changed = True

        if o5 is None and len(trading_dates) >= 6:
            p5 = _price_on_date(cur, trading_dates[5])
            if p5:
                updates["outcome_pct_5d"] = round((p5 - price_at_news) / price_at_news * 100, 2)
                changed = True

        fully_done = False
        if len(trading_dates) >= 21:
            p20 = _price_on_date(cur, trading_dates[20])
            if p20:
                updates["outcome_pct_20d"] = round((p20 - price_at_news) / price_at_news * 100, 2)
                changed = True
                fully_done = True

        if changed:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            vals = list(updates.values())
            if fully_done:
                set_clause += ", fully_evaluated=1"
            vals.append(news_id)
            cur.execute(f"UPDATE daily_news SET {set_clause} WHERE id=?", vals)
            updated += 1

    conn.commit()
    conn.close()
    return updated


def news_impact_summary(db_path=None):
    """میانگین تأثیر خبرهای کامل‌ارزیابی‌شده، تفکیک‌شده بر اساس (منبع، دسته)
    -- مثلاً «کدال / افزایش سرمایه» جدا از «کدال / گزارش فعالیت ماهانه».
    قاطی کردن انواع مختلف خبر کدال میانگین رو بی‌معنی می‌کنه، برای همین
    این تفکیک لازمه. فقط وقتی نمونه کافیه که ready=True می‌شه."""
    db_path = db_path or config.DATABASE_NAME
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT source, category, outcome_pct_1d, outcome_pct_5d, outcome_pct_20d "
        "FROM daily_news WHERE fully_evaluated=1"
    )
    rows = cur.fetchall()
    conn.close()

    by_group = {}
    for source, category, o1, o5, o20 in rows:
        key = (source, category or "سایر")
        by_group.setdefault(key, {"n": 0, "o1": [], "o5": [], "o20": []})
        by_group[key]["n"] += 1
        if o1 is not None:
            by_group[key]["o1"].append(o1)
        if o5 is not None:
            by_group[key]["o5"].append(o5)
        if o20 is not None:
            by_group[key]["o20"].append(o20)

    summary = {}
    for (source, category), d in by_group.items():
        avg = lambda lst: round(sum(lst) / len(lst), 2) if lst else None
        summary[(source, category)] = {
            "samples": d["n"],
            "ready": d["n"] >= MIN_SAMPLES,
            "avg_impact_1d": avg(d["o1"]),
            "avg_impact_5d": avg(d["o5"]),
            "avg_impact_20d": avg(d["o20"]),
        }
    return summary


if __name__ == "__main__":
    n = update_news_impact()
    print(f"{n} خبر آپدیت شد.")
    print("=" * 50)
    print("خلاصه‌ی تأثیر خبرها روی قیمت (بر اساس منبع + دسته)")
    print("=" * 50)
    summary = news_impact_summary()
    if not summary:
        print("هنوز هیچ خبری کامل ارزیابی نشده.")
    for (source, category), s in summary.items():
        label = {"codal": "کدال", "supervisor": "ناظر بازار"}.get(source, source)
        ready_txt = "✅ آماده" if s["ready"] else f"⏳ نیاز به {MIN_SAMPLES - s['samples']} نمونه‌ی دیگه"
        print(f"\n[{label} / {category}] نمونه‌ها: {s['samples']} | {ready_txt}")
        print(f"  میانگین تأثیر ۱ روزه:  {s['avg_impact_1d']}%")
        print(f"  میانگین تأثیر ۵ روزه:  {s['avg_impact_5d']}%")
        print(f"  میانگین تأثیر ۲۰ روزه: {s['avg_impact_20d']}%")