# -*- coding: utf-8 -*-
"""
تاریخچه‌ی فشار خرید/فروش (order_book) طی روز -- فقط خواندنی، هیچ اثری روی
سیگنال یا دیتابیس نداره.

هدف: وقتی داشبورد یه عدد عجیب نشون می‌ده (مثلاً فشار فروش شدید)، این اسکریپت
نشون می‌ده اون عدد مال چه ساعتی بوده و طی روز چطور تغییر کرده -- تا معلوم بشه
واقعیت بازار بوده (مثلاً فشار لحظه‌ی آخر/حراج) یا یه باگ داده‌ی اشتباه نشون داده.

اجرا:
    python check_order_book_history.py                 # هر سه نماد، امروز
    python check_order_book_history.py اهرم             # فقط اهرم، امروز
    python check_order_book_history.py اهرم 2026-09-06   # اهرم، یه روز خاص
"""
import sqlite3
import sys
from datetime import datetime

SYMBOL_DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db",
}


def classify(buy_vol, sell_vol, buy_cnt, sell_cnt):
    buy_empty = (buy_vol == 0 and buy_cnt == 0)
    sell_empty = (sell_vol == 0 and sell_cnt == 0)
    if buy_empty and sell_empty:
        return "NO_DATA", 0.0
    if sell_empty and not buy_empty:
        return "LOCKED_BUY_QUEUE (صف خرید قفل)", 100.0
    if buy_empty and not sell_empty:
        return "LOCKED_SELL_QUEUE (صف فروش قفل)", -100.0
    imbalance = (buy_vol - sell_vol) / (buy_vol + sell_vol) * 100
    if imbalance > 20:
        return "BUY_HEAVY (فشار خرید)", imbalance
    elif imbalance < -20:
        return "SELL_HEAVY (فشار فروش)", imbalance
    else:
        return "BALANCED (متعادل)", imbalance


def show_history(name, db_path, date_str):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as e:
        print(f"❌ نتونستم {db_path} رو باز کنم: {e}")
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT time,
                   SUM(buy_volume), SUM(sell_volume),
                   SUM(buy_count), SUM(sell_count)
            FROM order_book
            WHERE date(time) = ?
            GROUP BY time
            ORDER BY time ASC
            """,
            (date_str,),
        )
        rows = cur.fetchall()
    except Exception as e:
        print(f"❌ خطا خوندن order_book از {db_path}: {e}")
        conn.close()
        return
    conn.close()

    print(f"\n{'=' * 70}")
    print(f"📊 تاریخچه‌ی فشار خرید/فروش {name} -- {date_str}")
    print(f"{'=' * 70}")

    if not rows:
        print("   هیچ داده‌ای برای این روز پیدا نشد.")
        return

    for time_str, buy_vol, sell_vol, buy_cnt, sell_cnt in rows:
        buy_vol = buy_vol or 0
        sell_vol = sell_vol or 0
        buy_cnt = buy_cnt or 0
        sell_cnt = sell_cnt or 0
        label, imbalance = classify(buy_vol, sell_vol, buy_cnt, sell_cnt)
        clock = time_str.split(" ")[-1] if " " in time_str else time_str
        print(f"   {clock}  |  {label:35s}  |  imbalance={imbalance:+.1f}%  "
              f"|  buy_vol={buy_vol:,.0f}  sell_vol={sell_vol:,.0f}")


if __name__ == "__main__":
    args = sys.argv[1:]
    symbol_arg = None
    date_arg = datetime.now().strftime("%Y-%m-%d")

    for a in args:
        if a in SYMBOL_DBS:
            symbol_arg = a
        else:
            date_arg = a  # فرض می‌کنیم فرمت YYYY-MM-DD داده شده

    targets = {symbol_arg: SYMBOL_DBS[symbol_arg]} if symbol_arg else SYMBOL_DBS

    for name, db in targets.items():
        show_history(name, db, date_arg)

    print(f"\n{'=' * 70}")
    print("توجه: این عددها مستقیم از خودِ order_book میان، دست‌نخورده -- همون")
    print("چیزی که order_book.py هر سیکل ذخیره می‌کنه. اگه یه ساعت خاص عدد")
    print("عجیب داره ولی ساعت‌های اطرافش طبیعی‌ان، احتمالاً واقعیت بازار بوده")
    print("(مثلاً فشار لحظه‌ی آخر/حراج)، نه باگ.")
    print(f"{'=' * 70}")