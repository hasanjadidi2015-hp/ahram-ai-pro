# -*- coding: utf-8 -*-
"""
اصلاح یک ردیف: پوزیشن ضهرم8032 (ورود ۵۲۰۱) که به‌اشتباه با نیمه‌ی سود حساب شد.
فقط ردیف‌های همین position_id را تغییر می‌دهد، با پشتیبان قبل از تغییر.

اجرا (کنار ahram_v2.db، با ربات بسته):
    python fix_ahram_8032.py            <- پیش‌نمایش؛ هیچ تغییری نمی‌دهد
    python fix_ahram_8032.py --apply    <- پشتیبان می‌گیرد و اصلاح می‌کند
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

DB = "ahram_v2.db"
APPLY = "--apply" in sys.argv
SYMBOL = "ضهرم8032"
ENTRY = 5201.0
CLOSE_PRICE = 10801.0          # قیمت خروج ثبت‌شده در لحظه‌ی بسته شدن (۱۲:۱۴:۱۱)
CORRECT_PCT = round((CLOSE_PRICE / ENTRY - 1) * 100, 1)   # ۱۰۷٫۷

if not os.path.exists(DB):
    print(f"{DB} پیدا نشد")
    sys.exit(1)

conn = sqlite3.connect(DB)
rows = conn.execute(
    "SELECT s.position_id, s.option_symbol, s.option_price, s.outcome, s.outcome_pct, s.outcome_time "
    "FROM signal_history s WHERE s.option_symbol=? AND s.outcome='WIN' AND s.outcome_pct BETWEEN 53.7 AND 53.9 "
    "AND s.option_price=?",
    (SYMBOL, ENTRY),
).fetchall()
print("=" * 60)
print("حالت: " + ("اعمال (با پشتیبان)" if APPLY else "پیش‌نمایش (هیچ تغییری نمی‌شود)"))
print("=" * 60)
if len(rows) == 0:
    print("ردیفی با این مشخصات پیدا نشد. هیچ کاری نشد.")
    conn.close()
    sys.exit(0)
if len({r[0] for r in rows}) != 1:
    print("بیش از یک پوزیشن پیدا شد؛ برای ایمنی هیچ تغییری نمی‌دهم.")
    for r in rows:
        print("  ", r)
    conn.close()
    sys.exit(1)

pid = rows[0][0]
print(f"position_id: {pid}")
print(f"نتیجه‌ی فعلی: WIN {rows[0][4]}٪ (خروج {rows[0][5]})")
print(f"نتیجه‌ی درست: WIN {CORRECT_PCT}٪ (قیمت خروج {CLOSE_PRICE:.0f} از ورود {ENTRY:.0f})")
all_rows = conn.execute("SELECT id, outcome, outcome_pct FROM signal_history WHERE position_id=?", (pid,)).fetchall()
print(f"ردیف‌هایی که تغییر می‌کنند: {len(all_rows)} (همه‌ی ردیف‌های این پوزیشن)")

if APPLY:
    conn.close()
    backup = f"{DB}.backup_fix8032_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(DB, backup)
    print(f"پشتیبان: {backup}")
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE signal_history SET outcome_pct=? WHERE position_id=?", (CORRECT_PCT, pid))
    conn.commit()
    after = conn.execute("SELECT outcome, outcome_pct FROM signal_history WHERE position_id=? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    print(f"✅ بعد از اصلاح: {after[0]} {after[1]}٪")
    conn.close()
else:
    conn.close()
    print("برای اعمال: python fix_ahram_8032.py --apply")
print("=" * 60)