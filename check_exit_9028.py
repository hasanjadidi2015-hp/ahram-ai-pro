# -*- coding: utf-8 -*-
"""
بررسی فقط‌خواندنی معامله‌ی طهرم9028 (زیان ۳۶.۷٪ در ۲۸ مهر).
هیچ چیزی را تغییر نمی‌دهد.
اجرا (کنار ahram_v2.db):
    python check_exit_9028.py
خروجی در check_exit_9028.txt
"""
import sqlite3
import os

SYMBOL = "\u0637\u0647\u0631\u0645" + "9028"   # طهرم9028
DB = "ahram_v2.db"
DAY = "2026-10-19"
OUT = "check_exit_9028.txt"
lines = []


def out(s=""):
    print(s)
    lines.append(str(s))


if not os.path.exists(DB):
    out(f"{DB} پیدا نشد -- این فایل را کنار ahram_v2.db اجرا کن")
else:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = conn.cursor()

    out("=== ۱) قیمت‌های ثبت‌شده در جدول options (ترتیب زمانی) ===")
    try:
        rows = cur.execute(
            "SELECT time, option_price, stock_price FROM options "
            "WHERE symbol=? AND date(time)=? ORDER BY id",
            (SYMBOL, DAY),
        ).fetchall()
        out(f"تعداد ردیف: {len(rows)}")
        for r in rows[:60]:
            out(f"  {r[0]} | قیمت اختیار={r[1]} | قیمت سهم={r[2]}")
        if len(rows) > 60:
            out(f"  ... و {len(rows) - 60} ردیف دیگر")
    except Exception as e:
        out(f"خطا: {e}")

    out("\n=== ۲) ردیف‌های سیگنال این نماد (امروز و دیروز) ===")
    try:
        rows = cur.execute(
            "SELECT time, signal_type, option_price, stop_loss, target1, outcome, outcome_pct, position_id "
            "FROM signal_history WHERE option_symbol=? AND date(time) IN (?, date(?, '-1 day')) "
            "ORDER BY id",
            (SYMBOL, DAY, DAY),
        ).fetchall()
        out(f"تعداد ردیف: {len(rows)}")
        for r in rows[-40:]:
            out(f"  {r}")
    except Exception as e:
        out(f"خطا: {e}")

    conn.close()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nنتیجه در فایل {OUT} ذخیره شد -- اونو برام بفرست.")