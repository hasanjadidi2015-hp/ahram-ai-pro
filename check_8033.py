# -*- coding: utf-8 -*-
"""
بررسی فقط‌خواندنی وضعیت پوزیشن طهرم8033 در ahram_v2.db (بدون تغییر دیتا).
اجرا (کنار ahram_v2.db):  python check_8033.py
خروجی: check_8033.txt
"""
import sqlite3
import os

SYMBOL = "\u0637\u0647\u0631\u0645" + "8033"   # طهرم8033
DB = "ahram_v2.db"
OUT = "check_8033.txt"
lines = []


def out(s=""):
    print(s)
    lines.append(str(s))


if not os.path.exists(DB):
    out(f"{DB} پیدا نشد")
else:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(signal_history)").fetchall()]
    want = [c for c in ("id", "time", "signal_type", "option_price", "stop_loss", "target1",
                        "outcome", "outcome_pct", "outcome_time", "evaluated_at", "position_id")
            if c in cols]
    out(f"ستون‌های موجود: {', '.join(want)}")
    rows = cur.execute(
        f"SELECT {', '.join(want)} FROM signal_history WHERE option_symbol=? ORDER BY id",
        (SYMBOL,),
    ).fetchall()
    out(f"تعداد ردیف‌های {SYMBOL}: {len(rows)}")
    for r in rows:
        out("  " + " | ".join(str(x) for x in r))
    conn.close()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nنتیجه در فایل {OUT} ذخیره شد -- اونو برام بفرست.")