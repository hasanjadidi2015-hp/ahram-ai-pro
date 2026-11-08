# -*- coding: utf-8 -*-
"""
شبیه‌سازی قانون خروج جدید شما (فقط خواندنی، بدون حد ضرر):
  - ورود: قیمت آپشن در ردیف سیگنال خرید
  - نصف پوزیشن در رسیدن به +TP1 (پیش‌فرض ۲۰٪) بسته می‌شود
  - نصف دیگر در رسیدن به +TP2 (پیش‌فرض ۳۰٪ و ۴۰٪ هر دو گزارش می‌شوند)
  - اگر TP2 نرسید، نصف باقی در آخرین قیمت معتبر پنجره‌ی نگهداری بسته می‌شود
  - پنجره‌ی نگهداری: حداکثر MAX_HOLD_DAYS روز تقویمی بعد از ورود
  - فقط قیمت‌های تازه، با حداقل معامله و قیمت معتبر
  - حد ضرر نداریم؛ زیان فقط از قیمت پایان پنجره محاسبه می‌شود

این شبیه‌سازی نشان می‌دهد با قانون شما روی سیگنال‌های واقعی چه نتیجه‌ای می‌گرفتیم.
اجرا: python exit_sim.py
"""
import os
import sqlite3
from datetime import datetime, timedelta

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-11-01"
MIN_OPTION_PRICE = 10.0
MIN_TRADES = 5
MAX_HOLD_DAYS = 2
TP1_PCT = 20.0
TP2_LIST = [30.0, 40.0]


def parse(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def fresh(row, has_trades):
    _t, price, fr, trades, vol = row
    if price is None or float(price) < MIN_OPTION_PRICE or fr != 1:
        return False
    return (trades or 0) >= MIN_TRADES if has_trades else (vol or 0) > 0


def window_prices(conn, sym, t0, has_trades):
    end = (t0 + timedelta(days=MAX_HOLD_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    q = ("SELECT time, option_price, price_fresh, " + ("trades_count" if has_trades else "NULL") +
         ", volume FROM options WHERE symbol=? AND time>=? AND time<=? AND option_price>=? ORDER BY id")
    rows = conn.execute(q, (sym, t0.strftime("%Y-%m-%d %H:%M:%S"), end, MIN_OPTION_PRICE)).fetchall()
    return [float(r[1]) for r in rows if fresh(r, has_trades)]


def simulate(entry, prices, tp2_pct):
    """برمی‌گرداند (درصد کل پوزیشن، آیا TP1 رسید، آیا TP2 رسید)"""
    if not prices:
        return None
    tp1 = entry * (1 + TP1_PCT / 100)
    tp2 = entry * (1 + tp2_pct / 100)
    half1 = None
    half2 = None
    for p in prices:
        if half1 is None and p >= tp1:
            half1 = TP1_PCT
        if half2 is None and p >= tp2:
            half2 = tp2_pct
        if half1 is not None and half2 is not None:
            break
    last = (prices[-1] / entry - 1) * 100
    h1 = half1 if half1 is not None else last
    h2 = half2 if half2 is not None else last
    total = 0.5 * h1 + 0.5 * h2
    return total, half1 is not None, half2 is not None


print("=" * 72)
print(f"شبیه‌سازی قانون خروج: نصف در +{TP1_PCT:.0f}٪، نصف در +TP2 | نگهداری تا {MAX_HOLD_DAYS} روز | بدون حد ضرر")
print(f"داده‌ی معتبر از {START_DATE}")
print("=" * 72)

results = {tp2: [] for tp2 in TP2_LIST}
reach1 = 0
n_eval = 0
for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    has_trades = "trades_count" in cols
    sigs = conn.execute(
        "SELECT time, option_symbol, option_price FROM signal_history "
        "WHERE time>=? AND signal_type IN ('BUY_CALL','BUY_PUT') AND option_symbol IS NOT NULL "
        "AND option_price>=? ORDER BY time", (START_DATE, MIN_OPTION_PRICE)).fetchall()
    for t_sig, osym, entry in sigs:
        t0 = parse(t_sig)
        if t0 is None:
            continue
        prices = window_prices(conn, osym, t0, has_trades)
        if not prices:
            continue
        n_eval += 1
        for tp2 in TP2_LIST:
            r = simulate(float(entry), prices, tp2)
            if r:
                results[tp2].append(r[0])
                if tp2 == TP2_LIST[0]:
                    reach1 += 1 if r[1] else 0
    conn.close()

print(f"سیگنال‌های قابل ارزیابی: {n_eval}")
if n_eval == 0:
    print("داده‌ی کافی نیست.")
else:
    print(f"رسیدن به +{TP1_PCT:.0f}٪ در پنجره: {reach1} از {n_eval} ({reach1 / n_eval * 100:.0f}٪)")
    print("-" * 72)
    for tp2 in TP2_LIST:
        vals = results[tp2]
        if not vals:
            continue
        wins = sum(1 for v in vals if v > 0)
        avg = sum(vals) / len(vals)
        print(f"خروج نصف در +{TP1_PCT:.0f}٪ و نصف در +{tp2:.0f}٪:")
        print(f"   میانگین نتیجه‌ی هر پوزیشن: {avg:+.1f}٪ | سودده: {wins} از {len(vals)}")
        print(f"   (قبل از کارمزد و اسپرد)")
    print("-" * 72)
    print("توجه: این شبیه‌سازی روی همان سیگنال‌های ربات است. هنوز تعداد کمی دارد و هزینه‌ها را لحاظ نمی‌کند.")
print("=" * 72)