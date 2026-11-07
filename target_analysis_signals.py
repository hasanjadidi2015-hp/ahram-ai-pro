# -*- coding: utf-8 -*-
"""
تحلیل اهداف نوسان‌گیری روی داده‌ی تاریخی (فقط خواندنی).

برای هر پوزیشن ربات (هر position_id، از اولین ردیف):
  - ورود = قیمت آپشن در اولین ردیف
  - از ورود تا MAX_HOLD_DAYS روز بعد، قیمت‌های تازه‌ی آن قرارداد بررسی می‌شود
  - قیمت فقط وقتی معتبر است که >= MIN_OPTION_PRICE و price_fresh=1 و (اگر ستون بود) تعداد معامله >= MIN_TRADES
  - می‌شمارد: آیا قیمت به +X٪ رسیده، قبل از اینکه به -STOP٪ برسد؟
  - برای هر هدف احتمال «رسیدن قبل از حد ضرر» و میانه‌ی بیشترین سود را گزارش می‌کند

این تحلیل نشان می‌دهد هدف‌های واقعی‌تر چقدر شانس دارند. قانون معامله را تغییر نمی‌دهد.

اجرا (کنار فایل‌های .db):
    python target_analysis.py
"""
import os
import sqlite3
import statistics
from datetime import datetime, timedelta

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-11-01"  # داده‌ی قابل اعتماد از این تاریخ (price_time و trades_count درست ثبت می‌شوند)
MIN_OPTION_PRICE = 10.0
MIN_TRADES = 5
MAX_HOLD_DAYS = 2
STOP_PCT = 15.0
TARGETS = [10, 20, 25, 30, 40, 50]

POS_SQL = """
SELECT s.position_id, s.time, s.option_price, s.option_symbol, s.signal_type
FROM signal_history s
WHERE s.time >= ? AND s.option_price >= ?
  AND s.signal_type IN ('BUY_CALL','BUY_PUT')
  AND s.option_symbol IS NOT NULL
ORDER BY s.time
"""


def parse(ts):
    txt = str(ts).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(txt[:len(fmt) + 2 if fmt.endswith('%S') else 16], fmt)
        except (ValueError, TypeError):
            continue
    return None


def path_after(conn, sym, t0, has_trades):
    """قیمت‌های تازه و معتبر آن قرارداد، از ورود تا MAX_HOLD_DAYS روز بعد، به ترتیب زمان."""
    end = (t0 + timedelta(days=MAX_HOLD_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    q = ("SELECT time, option_price, price_fresh" + (", trades_count" if has_trades else "") +
         " FROM options WHERE symbol=? AND time>=? AND time<=? AND option_price>=?" +
         " ORDER BY id")
    rows = conn.execute(q, (sym, t0.strftime("%Y-%m-%d %H:%M:%S"), end, MIN_OPTION_PRICE)).fetchall()
    out = []
    for r in rows:
        if r[2] != 1:
            continue
        if has_trades and (r[3] or 0) < MIN_TRADES:
            continue
        out.append((parse(r[0]), float(r[1])))
    return out


def analyze_position(entry, path):
    """بیشترین سود، و برای هر هدف: آیا قبل از حد ضرر رسیده؟"""
    if not path:
        return None
    max_up = 0.0
    hit = {t: None for t in TARGETS}  # True / False
    stop_level = entry * (1 - STOP_PCT / 100)
    for _, p in path:
        up = (p / entry - 1) * 100
        max_up = max(max_up, up)
        for t in TARGETS:
            if hit[t] is None:
                if up >= t:
                    hit[t] = True
                elif p <= stop_level:
                    hit[t] = False
        if all(v is not None for v in hit.values()):
            break
    for t in TARGETS:
        if hit[t] is None:
            hit[t] = False  # نه به هدف رسید نه به حد ضرر: حساب به‌نفع هدف نیست
    return max_up, hit


results = []
print("=" * 70)
print(f"تحلیل اهداف (همه‌ی سیگنال‌های خرید) | از {START_DATE} | حد ضرر {STOP_PCT:.0f}٪ | نگهداری تا {MAX_HOLD_DAYS} روز")
print("=" * 70)

for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    has_trades = "trades_count" in cols
    if not has_trades:
        print(f"⚠️ {name}: ستون trades_count نیست؛ فیلتر حجم اعمال نشد")
    rows = conn.execute(POS_SQL, (START_DATE, MIN_OPTION_PRICE)).fetchall()
    n_used = 0
    for pid, t0s, entry, sym, typ in rows:
        t0 = parse(t0s)
        if t0 is None:
            continue
        r = analyze_position(float(entry), path_after(conn, sym, t0, has_trades))
        if r is None:
            continue
        n_used += 1
        results.append((name, sym, t0s, float(entry), r[0], r[1], pid, typ))
    conn.close()
    print(f"{name}: {len(rows)} ردیف سیگنال خرید | قابل ارزیابی (داده‌ی تازه و معتبر): {n_used}")

print("-" * 70)
n = len(results)
if n == 0:
    print("داده‌ی کافی برای تحلیل نیست.")
else:
    n_pos = len({r[6] for r in results})
    n_call = sum(1 for r in results if r[7] == "BUY_CALL")
    n_put = sum(1 for r in results if r[7] == "BUY_PUT")
    print(f"جمع ردیف‌های سیگنال قابل ارزیابی: {n} (کال: {n_call} | پوت: {n_put})")
    print(f"پوزیشن‌های یکتا در بین آن‌ها: {n_pos}")
    print("توجه: هر پوزیشن ممکن است چند ردیف سیگنال داشته باشد؛ ردیف‌ها هم‌بسته‌اند و مستقل نیستند.")
    print(f"{'هدف':>6} | {'رسید قبل از حد ضرر':>20} | {'درصد':>6}")
    for t in TARGETS:
        cnt = sum(1 for r in results if r[5][t])
        print(f"+{t:>4}٪ | {cnt:>20} | {cnt / n * 100:>5.0f}٪")
    ups = [r[4] for r in results]
    print(f"میانه‌ی بیشترین سود هر پوزیشن: {statistics.median(ups):.1f}٪")
    print(f"بیشترین سود دیده‌شده: {max(ups):.1f}٪")
    print("-" * 70)
    print("هر پوزیشن (نماد | ورود | بیشترین سود | رسیده به +۲۵٪ قبل از حد ضرر؟):")
    for name, sym, t0s, entry, up, hit, pid, typ in results:
        print(f"  {name} | {typ} | {sym} | {t0s} | ورود {entry:.0f} | بیشترین {up:+.1f}٪ | +25٪: {'بله' if hit[25] else 'خیر'}")
print("=" * 70)
print("توجه: سیگنال‌های «تحت نظر» (WATCH) در این تحلیل نیستند، چون قرارداد مشخصی ندارند و ورودی به حساب نمی‌آیند.")
print("توجه: قیمت‌های غیرتازه و کم‌معامله کنار گذاشته شدند.")