# -*- coding: utf-8 -*-
"""
غربال پتانسیل به تفکیک نوع بازار (فقط خواندنی).

نوع بازار در لحظه‌ی ورود، فقط با داده‌ی همان لحظه و روزهای قبل تعیین می‌شود (بدون نگاه به آینده):
  - بازار صعودی: بسته‌ی دو روز معاملاتی قبل نسبت به بسته‌ی سه روز قبل بیشتر از +UP_PCT٪
  - بازار نزولی: کمتر از -DOWN_PCT٪
  - بازار رنج/نوسانی: بین این دو
  (بسته‌ی هر روز = آخرین قیمت سهم پایه همان روز در جدول options)

سپس برای هر نوع بازار و هر نوع قرارداد (کال / پوت) نرخ رسیدن به +۲۰ / +۳۰ / +۴۰٪ در ۲ روز را نشان می‌دهد.
این همان قانون نانوشته‌ی شماست که با داده سنجیده می‌شود.

هشدار: داده از START_DATE به بعد است؛ تعداد روزها کم است و هر نوع بازار ممکن است روز کمی داشته باشد.

اجرا (کنار فایل‌های .db):
    python regime_screen.py
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
UP_PCT = 1.5
DOWN_PCT = 1.5


def parse(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def regime_for(day_closes, day):
    """day_closes: dict روز -> بسته‌ی سهم. فقط روزهای قبل از day استفاده می‌شوند."""
    past = sorted(d for d in day_closes if d < day)
    if len(past) < 3:
        return None
    c_now = day_closes[past[-1]]     # بسته‌ی دو روز قبل از روز ورود (آخرین روز کامل)
    c_then = day_closes[past[-3]]
    if not c_then:
        return None
    r = (c_now / c_then - 1) * 100
    if r > UP_PCT:
        return "صعودی"
    if r < -DOWN_PCT:
        return "نزولی"
    return "رنج/نوسانی"


rows = []  # (regime, type, hits)
for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    has_trades = "trades_count" in cols
    tc = "trades_count" if has_trades else "NULL"
    base = conn.execute(
        f"SELECT time, symbol, option_type, stock_price, option_price, price_fresh, {tc}, volume "
        f"FROM options WHERE time>=? ORDER BY id", (START_DATE,)).fetchall()
    # بسته‌ی روزانه‌ی سهم پایه (آخرین قیمت سهم پایه هر روز)
    # هر فایل دیتابیس یک سهم پایه است؛ بسته‌ی روزانه‌ی همان سهم
    series = {}
    for t, sym, typ, stock, opt, fr, trades, vol in base:
        d = str(t)[:10]
        if stock:
            series[d] = float(stock)
    by_sym = defaultdict(list)
    for t, sym, typ, stock, opt, fr, trades, vol in base:
        if fr != 1 or float(opt or 0) < MIN_OPTION_PRICE:
            continue
        if has_trades and (trades or 0) < MIN_TRADES:
            continue
        if not has_trades and (vol or 0) <= 0:
            continue
        by_sym[(sym, typ)].append((parse(t), typ, float(opt), str(t)[:10]))
    for key, lst in by_sym.items():
        lst.sort(key=lambda x: x[0] or datetime.min)
        for i, (t0, typ, p0, day) in enumerate(lst):
            if t0 is None:
                continue
            reg = regime_for(series, day)
            if reg is None:
                continue
            end = t0 + timedelta(days=HORIZON_DAYS)
            future = [x[2] for x in lst[i + 1:] if x[0] and t0 < x[0] <= end]
            if not future:
                continue
            hits = {tg: any(f >= p0 * (1 + tg / 100) for f in future) for tg in TARGETS}
            rows.append((reg, "کال" if typ == "CALL" else "پوت", hits, key[0], day))
    conn.close()

print("=" * 72)
print(f"بررسی تمرکز: غربال به تفکیک نوع بازار | از {START_DATE} | افق {HORIZON_DAYS} روز")
print("=" * 72)
if not rows:
    print("داده‌ی کافی نیست.")
else:
    groups = defaultdict(list)
    for reg, typ, hits, sym, day in rows:
        groups[(reg, typ)].append((hits, sym, day))
    for reg in ["صعودی", "رنج/نوسانی", "نزولی"]:
        for typ in ["کال", "پوت"]:
            items = groups.get((reg, typ), [])
            if not items:
                print(f"{reg:<12} {typ:<4}  هیچ داده‌ای نیست")
                continue
            m = len(items)
            contracts = defaultdict(int)
            days = set()
            for _h, sym, day in items:
                contracts[sym] += 1
                days.add(day)
            top = sorted(contracts.values(), reverse=True)
            top5_share = sum(top[:5]) / m * 100
            # نرخ بر اساس قرارداد: هر قرارداد یک بار شمرده می‌شود (آیا حداقل یک بار به هدف رسیده)
            per_c = defaultdict(lambda: {tg: False for tg in TARGETS})
            for h, sym, _d in items:
                for tg in TARGETS:
                    per_c[sym][tg] = per_c[sym][tg] or h[tg]
            nc = len(per_c)
            rates = " | ".join(
                f"+{tg}٪: {sum(1 for c in per_c.values() if c[tg]) / nc * 100:3.0f}٪" for tg in TARGETS)
            print(f"{reg:<12} {typ:<4} لحظه‌ها: {m:>5} | قرارداد: {nc:>3} | روز: {len(days):>2} | "
                  f"۵ قرارداد پرتکرار: {top5_share:4.0f}٪")
            print(f"             نرخ بر اساس قرارداد (هر قرارداد یک بار): {rates}")
    print("-" * 72)
    print("راهنما:")
    print("  - اگر تعداد قرارداد کم یا سهم ۵ قرارداد پرتکرار بالا باشد، نتیجه‌ی آن گروه تکی است.")
    print("  - نرخ بر اساس قرارداد مهم‌تر است، چون هر قرارداد یک بار شمرده می‌شود.")
    print("  - برای تأیید قانون، هر گروه باید چند روز مختلف و چند ده قرارداد داشته باشد.")
print("=" * 72)