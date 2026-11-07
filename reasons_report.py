# -*- coding: utf-8 -*-
"""
گزارش «چرا این سیگنال‌ها قابل ارزیابی نیستند» (فقط خواندنی).

برای هر ردیف سیگنال خرید (BUY_CALL / BUY_PUT) از START_DATE به بعد، آخرین ردیف قیمت همان
قرارداد در options تا لحظه‌ی سیگنال را پیدا می‌کند و اولین دلیلی که سیگنال را غیرقابل ارزیابی
می‌کند ثبت می‌کند. دلیل‌ها به ترتیب:
  1. قیمت ورود نامعتبر (کمتر از MIN_OPTION_PRICE)
  2. هیچ ردیف قیمتی برای این قرارداد قبل از سیگنال نیست
  3. قیمت غیرتازه (price_fresh != 1)
  4. حجم/معامله‌ی کم (trades_count < MIN_TRADES)
  5. قابل ارزیابی

اجرا (کنار فایل‌های .db):
    python reasons_report.py
"""
import os
import sqlite3
from collections import Counter, defaultdict

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-11-01"  # داده‌ی قابل اعتماد از این تاریخ (price_time و trades_count درست ثبت می‌شوند)
MIN_OPTION_PRICE = 10.0
MIN_TRADES = 5
SAMPLE = 3

REASONS = {
    "bad_price": "قیمت ورود نامعتبر",
    "no_price": "قیمت قبل از سیگنال نیست",
    "stale": "قیمت غیرتازه",
    "low_trades": "معامله‌ی کم (کمتر از حداقل)",
    "ok": "قابل ارزیابی",
}

SIG_SQL = """
SELECT id, time, symbol, signal_type, option_symbol, option_price
FROM signal_history
WHERE time >= ? AND signal_type IN ('BUY_CALL','BUY_PUT') AND option_symbol IS NOT NULL
ORDER BY time
"""


def classify(conn, sym, t_sig, entry, has_trades):
    if entry is None or float(entry) < MIN_OPTION_PRICE:
        return "bad_price", None
    q = ("SELECT time, option_price, price_fresh" + (", trades_count" if has_trades else "") +
         " FROM options WHERE symbol=? AND time<=? ORDER BY id DESC LIMIT 1")
    row = conn.execute(q, (sym, t_sig)).fetchone()
    if not row:
        return "no_price", None
    if row[2] != 1:
        return "stale", row
    if has_trades and (row[3] or 0) < MIN_TRADES:
        return "low_trades", row
    return "ok", row


print("=" * 70)
print(f"گزارش دلیل کنار رفتن سیگنال‌های خرید | از {START_DATE}")
print("=" * 70)

total = Counter()
by_symbol = defaultdict(Counter)
by_type = defaultdict(Counter)
samples = defaultdict(list)

for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    has_trades = "trades_count" in cols
    if not has_trades:
        print(f"⚠️ {name}: ستون trades_count نیست؛ شرط حجم اعمال نشد")
    for sid, t_sig, sym, typ, osym, entry in conn.execute(SIG_SQL, (START_DATE,)).fetchall():
        reason, row = classify(conn, osym, t_sig, entry, has_trades)
        total[reason] += 1
        by_symbol[name][reason] += 1
        by_type[typ][reason] += 1
        if len(samples[reason]) < SAMPLE:
            samples[reason].append(f"{name} | {typ} | {osym} | {t_sig} | ورود {entry}"
                                   + (f" | آخرین قیمت قبل: {row[1]} در {row[0]}" if row else ""))
    conn.close()

n = sum(total.values())
print(f"جمع ردیف‌های سیگنال خرید: {n}")
print("-" * 70)
for key in ["bad_price", "no_price", "stale", "low_trades", "ok"]:
    c = total.get(key, 0)
    pct = (c / n * 100) if n else 0
    print(f"{REASONS[key]:<32} {c:>6}  ({pct:5.1f}٪)")
print("-" * 70)
print("به تفکیک نماد:")
for name in by_symbol:
    parts = " | ".join(f"{REASONS[k]}: {by_symbol[name][k]}" for k in REASONS if by_symbol[name][k])
    print(f"  {name}: {parts}")
print("به تفکیک نوع:")
for typ in by_type:
    parts = " | ".join(f"{REASONS[k]}: {by_type[typ][k]}" for k in REASONS if by_type[typ][k])
    print(f"  {typ}: {parts}")
print("-" * 70)
print("نمونه‌ها:")
for key in ["stale", "low_trades", "no_price", "bad_price", "ok"]:
    for s in samples.get(key, []):
        print(f"  [{REASONS[key]}] {s}")
print("=" * 70)
print("توجه: این گزارش فقط می‌گوید هر سیگنال چرا کنار رفته؛ چیزی را تغییر نمی‌دهد.")