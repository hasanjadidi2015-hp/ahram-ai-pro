# -*- coding: utf-8 -*-
"""
بازبینی تازگی قیمت‌های گذشته (فقط خواندنی).

ستون price_fresh در داده‌ی قدیمی درست ثبت نشده. این اسکریپت تازگی را از خود داده دوباره حساب می‌کند:
  - تازگی = زمان آخرین معامله (price_time) نزدیک زمان ثبت ردیف (تا ۳۰ دقیقه، با تحمل ۵ دقیقه)
  - و قرارداد در همان روز معامله داشته باشد (trades_count یا حجم > ۰)
  - و قیمت >= ۱۰ ریال

سپس برای هر سیگنال خرید، آخرین قیمت قبل از سیگنال را با این قاعده‌ی تازه می‌سنجد و
با قاعده‌ی ذخیره‌شده مقایسه می‌کند.

اجرا (کنار فایل‌های .db):
    python recheck_freshness.py
"""
import os
import sqlite3
from collections import Counter
from datetime import datetime

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-08-01"
MIN_OPTION_PRICE = 10.0
MIN_TRADES = 5
MAX_AGE_MIN = 30.0
CLOCK_TOL_MIN = 5.0


def parse(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def parse_hhmmss(day_ts, hhmmss):
    """زمان HHMMSS را روی روز ردیف قرار می‌دهد."""
    d = parse(day_ts)
    s = str(hhmmss or "").strip().split(".")[0]
    if d is None or not s.isdigit():
        return None
    s = s.zfill(6)
    try:
        return d.replace(hour=int(s[0:2]), minute=int(s[2:4]), second=int(s[4:6]))
    except ValueError:
        return None


def fresh_recomputed(row, has_trades):
    """row: (time, option_price, price_time, volume, trades_count)"""
    t_row, price, p_time, volume, trades = row
    if price is None or float(price) < MIN_OPTION_PRICE:
        return False, "قیمت نامعتبر"
    t_price = parse_hhmmss(t_row, p_time)
    t_reg = parse(t_row)
    if t_price is None or t_reg is None:
        return False, "زمان نامعتبر"
    age = (t_reg - t_price).total_seconds() / 60
    if not (-CLOCK_TOL_MIN <= age <= MAX_AGE_MIN):
        return False, "زمان آخرین معامله قدیمی"
    if has_trades:
        if (trades or 0) < MIN_TRADES:
            return False, "معامله‌ی کم"
    else:
        if (volume or 0) <= 0:
            return False, "حجم صفر"
    return True, "تازه"


print("=" * 70)
print(f"بازبینی تازگی از داده‌ی خود قیمت‌ها | از {START_DATE}")
print("=" * 70)

agree = Counter()
recheck_total = Counter()
stored_total = Counter()
examples = []

for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    has_trades = "trades_count" in cols
    sel = "SELECT time, option_price, price_time, volume" + (", trades_count" if has_trades else ", NULL") + \
          ", price_fresh FROM options WHERE symbol=? AND time<=? ORDER BY id DESC LIMIT 1"
    sigs = conn.execute(
        "SELECT time, option_symbol, option_price, signal_type FROM signal_history "
        "WHERE time>=? AND signal_type IN ('BUY_CALL','BUY_PUT') AND option_symbol IS NOT NULL ORDER BY time",
        (START_DATE,)).fetchall()
    for t_sig, osym, entry, typ in sigs:
        row = conn.execute(sel, (osym, t_sig)).fetchone()
        if not row:
            recheck_total["بدون ردیف قیمت"] += 1
            stored_total["بدون ردیف قیمت"] += 1
            continue
        ok_new, why_new = fresh_recomputed(row[:5], has_trades)
        ok_old = (row[5] == 1) and (row[1] or 0) >= MIN_OPTION_PRICE
        recheck_total["قابل ارزیابی" if ok_new else why_new] += 1
        stored_total["قابل ارزیابی" if ok_old else "غیرتازه/نامعتبر (ذخیره‌شده)"] += 1
        agree[(ok_new, ok_old)] += 1
        if ok_new and not ok_old and len(examples) < 6:
            examples.append(f"{name} | {typ} | {osym} | {t_sig} | ورود {entry} | آخرین قیمت {row[1]} در {row[2]}")
    conn.close()

n = sum(agree.values()) + recheck_total.get("بدون ردیف قیمت", 0)
print(f"جمع سیگنال‌های خرید بررسی‌شده: {n}")
print("-" * 70)
print("با قاعده‌ی تازه (از خود داده):")
for k, v in recheck_total.most_common():
    print(f"   {k:<30} {v:>6}")
print("با قاعده‌ی ذخیره‌شده (ستون price_fresh):")
for k, v in stored_total.most_common():
    print(f"   {k:<30} {v:>6}")
print("-" * 70)
print("مقایسه:")
print(f"   هر دو قابل ارزیابی:              {agree[(True, True)]}")
print(f"   فقط قاعده‌ی تازه قابل ارزیابی:   {agree[(True, False)]}")
print(f"   فقط قاعده‌ی ذخیره‌شده:           {agree[(False, True)]}")
print(f"   هیچ‌کدام:                        {agree[(False, False)]}")
if examples:
    print("-" * 70)
    print("نمونه‌هایی که قاعده‌ی تازه قبول کرد و ذخیره‌شده رد کرد:")
    for e in examples:
        print("   " + e)
print("=" * 70)
print("توجه: این بازبینی چیزی را در دیتابیس تغییر نمی‌دهد؛ فقط تعداد واقعی سیگنال‌های قابل ارزیابی را می‌شمارد.")