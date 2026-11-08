# -*- coding: utf-8 -*-
"""
غربال پتانسیل قراردادها (فقط خواندنی).

برای هر ثبت قیمت تازه و معتبر از یک قرارداد (هر ردیف options)، می‌پرسیم:
آیا در ۲ روز بعد، قیمت تازه و معتبر همان قرارداد به +۲۰ / +۳۰ / +۴۰٪ رسیده؟
سپس نرخ این اتفاق را بر اساس ویژگی‌های همان لحظه (فاصله از قیمت سهم، روزهای مانده،
حجم معاملات، قیمت، نوع قرارداد، و نوسان اخیر سهم پایه) به تفکیک نشان می‌دهد.

تذکر: ردیف‌های یک قرارداد همبسته‌اند؛ این نتیجه‌ی غربال است، نه قانون قطعی.
داده از START_DATE به بعد (قبل از آن تازگی معتبر ثبت نشده).

اجرا (کنار فایل‌های .db):
    python screen_potential.py
"""
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-11-01"
MIN_OPTION_PRICE = 10.0
MIN_TRADES = 5
HORIZON_DAYS = 2
TARGETS = [20, 30, 40]


def parse(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def bucket_money(x):
    a = abs(x)
    if a < 2: return "نزدیک قیمت سهم (<۲٪)"
    if a < 5: return "۲ تا ۵٪"
    if a < 10: return "۵ تا ۱۰٪"
    return "بیشتر از ۱۰٪"


def bucket_dte(d):
    if d is None: return "نامشخص"
    if d <= 3: return "کمتر از ۴ روز"
    if d <= 10: return "۴ تا ۱۰ روز"
    if d <= 30: return "۱۰ تا ۳۰ روز"
    return "بیشتر از ۳۰ روز"


def bucket_trades(t):
    if t is None: return "نامشخص"
    if t < 20: return "کمتر از ۲۰"
    if t < 100: return "۲۰ تا ۱۰۰"
    if t < 500: return "۱۰۰ تا ۵۰۰"
    return "بیشتر از ۵۰۰"


def bucket_price(p):
    if p < 50: return "کمتر از ۵۰"
    if p < 200: return "۵۰ تا ۲۰۰"
    if p < 1000: return "۲۰۰ تا ۱۰۰۰"
    return "بیشتر از ۱۰۰۰"


def bucket_vol(v):
    if v is None: return "نامشخص"
    if v < 1: return "کم (<۱٪)"
    if v < 2: return "متوسط (۱ تا ۲٪)"
    return "بالا (>۲٪)"


rows_all = []  # (features, hits dict)
for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    has_trades = "trades_count" in cols
    tc = "trades_count" if has_trades else "NULL"
    base = conn.execute(
        f"SELECT id, time, symbol, option_type, stock_price, option_price, strike_price, days_to_expire, "
        f"price_fresh, {tc}, volume FROM options WHERE time>=? AND option_price>=? ORDER BY symbol, id",
        (START_DATE, MIN_OPTION_PRICE)).fetchall()
    # پیش‌بینی: ردیف‌های تازه و معتبر همان قرارداد، به ترتیب زمان
    by_sym = defaultdict(list)
    for r in base:
        if r[8] != 1:
            continue
        if has_trades and (r[9] or 0) < MIN_TRADES:
            continue
        if not has_trades and (r[10] or 0) <= 0:
            continue
        by_sym[r[2]].append(r)
    for sym, lst in by_sym.items():
        for i, r in enumerate(lst):
            t0 = parse(r[1])
            if t0 is None or not r[4] or not r[6]:
                continue
            end = t0 + timedelta(days=HORIZON_DAYS)
            future = [f[5] for f in lst[i + 1:] if parse(f[1]) and t0 < parse(f[1]) <= end]
            if not future:
                continue
            p0 = float(r[5])
            hits = {tg: any(fp >= p0 * (1 + tg / 100) for fp in future) for tg in TARGETS}
            # ویژگی سهم پایه: تغییر نسبی قیمت سهم نسبت به ردیف قبلی همین نماد (نوسان کوتاه)
            prev_stock = None
            for j in range(i - 1, -1, -1):
                if lst[j][4]:
                    prev_stock = float(lst[j][4])
                    break
            vol_pct = None
            if prev_stock and prev_stock > 0:
                vol_pct = abs(float(r[4]) / prev_stock - 1) * 100
            money = (float(r[6]) / float(r[4]) - 1) * 100
            if r[3] == "PUT":
                money = -money
            feats = {
                "نوع": "کال" if r[3] == "CALL" else "پوت",
                "فاصله از سهم": bucket_money(money),
                "روزهای مانده": bucket_dte(r[7]),
                "معامله‌ی امروز": bucket_trades(r[9] if has_trades else None),
                "قیمت قرارداد": bucket_price(float(r[5])),
                "نوسان سهم (تغییر آخرین ثبت)": bucket_vol(vol_pct),
            }
            rows_all.append((feats, hits))
    conn.close()

print("=" * 72)
print(f"غربال پتانسیل قراردادها | از {START_DATE} | افق {HORIZON_DAYS} روز")
print("=" * 72)
n = len(rows_all)
print(f"تعداد لحظه‌های قابل ارزیابی: {n}")
if n == 0:
    print("داده‌ی کافی نیست.")
else:
    base_rate = {tg: sum(1 for _, h in rows_all if h[tg]) / n * 100 for tg in TARGETS}
    print("نرخ پایه (همه‌ی لحظه‌ها): " + " | ".join(f"+{tg}٪: {base_rate[tg]:.0f}٪" for tg in TARGETS))
    print("-" * 72)
    feat_names = list(rows_all[0][0].keys())
    for fn in feat_names:
        print(f"بر اساس «{fn}»:")
        groups = defaultdict(list)
        for feats, hits in rows_all:
            groups[feats[fn]].append(hits)
        for g, hl in sorted(groups.items(), key=lambda x: -len(x[1])):
            m = len(hl)
            rates = " | ".join(f"+{tg}٪: {sum(1 for h in hl if h[tg]) / m * 100:3.0f}٪" for tg in TARGETS)
            print(f"   {g:<28} تعداد {m:>5} | {rates}")
        print()
    print("-" * 72)
    print("توجه: ردیف‌های یک قرارداد همبسته‌اند و تعداد هر گروه ممکن است از چند قرارداد بیاید.")
    print("نتیجه‌ی غربال را فقط زمانی معتبر بدانید که گروه‌های برتر تعداد و تنوع کافی داشته باشند.")
print("=" * 72)