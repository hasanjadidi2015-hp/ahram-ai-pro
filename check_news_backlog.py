# -*- coding: utf-8 -*-
"""
بررسی بک‌لاگ خبرهای ارزیابی‌نشده -- فقط خواندنی.
هدف: مطمئن شدن که این عدد بزرگ به‌خاطر خبر تکراری نیست، بلکه واقعاً
تعداد زیادی آیتم متفاوته که هنوز ۲۰ روز کاری ازشون نگذشته.

اجرا:
    python check_news_backlog.py
"""
import sqlite3

SYMBOL_DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db",
}


def check(name, db_path):
    print(f"\n{'=' * 70}")
    print(f"📰 بک‌لاگ خبر {name}")
    print(f"{'=' * 70}")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as e:
        print(f"❌ نتونستم {db_path} رو باز کنم: {e}")
        return
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM daily_news")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM daily_news WHERE fully_evaluated=0")
    unevaluated = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT item_id) FROM daily_news WHERE fully_evaluated=0")
    distinct_unevaluated = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM daily_news WHERE fully_evaluated=0 AND price_at_news IS NULL")
    no_price = cur.fetchone()[0]

    cur.execute("SELECT MIN(event_date), MAX(event_date) FROM daily_news WHERE fully_evaluated=0")
    oldest, newest = cur.fetchone()

    cur.execute("""
        SELECT source, category, COUNT(*) c
        FROM daily_news WHERE fully_evaluated=0
        GROUP BY source, category ORDER BY c DESC LIMIT 10
    """)
    top_categories = cur.fetchall()

    conn.close()

    print(f"   کل رکوردهای جدول: {total:,}")
    print(f"   ارزیابی‌نشده (fully_evaluated=0): {unevaluated:,}")
    print(f"   item_id متمایز در همون‌ها: {distinct_unevaluated:,}  "
          f"{'✅ برابرن -> تکراری نیست' if distinct_unevaluated == unevaluated else '⚠️ نابرابرن -> جای تعجب داره'}")
    print(f"   بدون قیمت ثبت‌شده (price_at_news NULL): {no_price:,}")
    print(f"   بازه‌ی تاریخ خبرهای ارزیابی‌نشده: {oldest} تا {newest}")
    print(f"\n   ۱۰ دسته‌ی پرتکرار:")
    for source, category, c in top_categories:
        print(f"      {source:10s} | {category or '(بدون دسته)':20s} | {c:,} تا")


if __name__ == "__main__":
    for name, db in SYMBOL_DBS.items():
        check(name, db)

    print(f"\n{'=' * 70}")
    print("راهنمای خوندن نتیجه:")
    print("- اگه 'item_id متمایز' == 'ارزیابی‌نشده' -> خبر تکراری نیست، حجم واقعیه")
    print("- اگه بازه‌ی تاریخ خیلی بیشتر از ۲۰ روز کاری عقب می‌ره -> یه‌جای")
    print("  ارزیابی (نه ثبت) گیر کرده، چون باید بعد از ۲۰ روز کاری خودکار خارج بشن")
    print(f"{'=' * 70}")