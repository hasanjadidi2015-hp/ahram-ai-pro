# -*- coding: utf-8 -*-
"""
گزارش هفتگی ربات از داده‌ی معتبر (فقط خواندنی، هیچ چیزی را تغییر نمی‌دهد).

فقط از START_DATE به بعد؛ چون قبل از آن، زمان آخرین معامله و تعداد معامله ثبت نمی‌شد.
سه بخش:
  ۱. سیگنال‌های خرید و دلیل قابل ارزیابی نبودن هر کدام
  ۲. نرخ رسیدن به اهداف (+۱۰ تا +۵۰٪) قبل از حد ضرر ۱۵٪، روی سیگنال‌های قابل ارزیابی
  ۳. پوزیشن‌های بسته و باز (با قیمت تازه)

خروجی روی صفحه + فایل weekly_summary_<تاریخ امروز>.txt

اجرا (کنار فایل‌های .db، بعد از بازار):
    python weekly_report.py
"""
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-11-01"
PARTIAL_START = "2026-11-04 00:00:00"  # از این زمان، هدف اول نیمه را می‌بندد
MIN_OPTION_PRICE = 10.0
MIN_TRADES = 5
MAX_HOLD_DAYS = 2
STOP_PCT = 15.0
TARGETS = [10, 20, 25, 30, 40, 50]
CLOSED = ("WIN", "LOSS", "BREAK_EVEN")
OPEN = ("PENDING", "T1_HIT")

lines = []


def out(s=""):
    print(s)
    lines.append(str(s))


def parse(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def fresh_row(row, has_trades):
    _t, price, fresh, trades, volume = row
    if price is None or float(price) < MIN_OPTION_PRICE or fresh != 1:
        return False
    if has_trades:
        return (trades or 0) >= MIN_TRADES
    return (volume or 0) > 0


def path_after(conn, sym, t0, has_trades):
    end = (t0 + timedelta(days=MAX_HOLD_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    q = ("SELECT time, option_price, price_fresh, " + ("trades_count" if has_trades else "NULL") +
         ", volume FROM options WHERE symbol=? AND time>=? AND time<=? AND option_price>=? ORDER BY id")
    rows = conn.execute(q, (sym, t0.strftime("%Y-%m-%d %H:%M:%S"), end, MIN_OPTION_PRICE)).fetchall()
    return [float(r[1]) for r in rows if fresh_row(r, has_trades)]


def hit_table(entry, prices):
    stop = entry * (1 - STOP_PCT / 100)
    hit = {t: None for t in TARGETS}
    for p in prices:
        up = (p / entry - 1) * 100
        for t in TARGETS:
            if hit[t] is None:
                if up >= t:
                    hit[t] = True
                elif p <= stop:
                    hit[t] = False
    return {t: bool(v) for t, v in hit.items()}


out("=" * 72)
out(f"گزارش هفتگی ربات | داده‌ی معتبر از {START_DATE} | تاریخ گزارش: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
out("=" * 72)

reasons_all = Counter()
eval_rows = []      # (نام، نوع، قرارداد، زمان، ورود، اهداف)
closed_all, open_all = [], []

for name, db in DBS:
    if not os.path.exists(db):
        out(f"\n{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    has_trades = "trades_count" in cols
    sigs = conn.execute(
        "SELECT time, signal_type, option_symbol, option_price FROM signal_history "
        "WHERE time>=? AND signal_type IN ('BUY_CALL','BUY_PUT') AND option_symbol IS NOT NULL ORDER BY time",
        (START_DATE,)).fetchall()
    sel = ("SELECT time, option_price, price_fresh, " + ("trades_count" if has_trades else "NULL") +
           ", volume FROM options WHERE symbol=? AND time<=? ORDER BY id DESC LIMIT 1")
    for t_sig, typ, osym, entry in sigs:
        if entry is None or float(entry) < MIN_OPTION_PRICE:
            reasons_all["قیمت ورود نامعتبر"] += 1
            continue
        row = conn.execute(sel, (osym, t_sig)).fetchone()
        if not row:
            reasons_all["قیمت قبل از سیگنال نیست"] += 1
            continue
        if not fresh_row(row, has_trades):
            reasons_all["قیمت غیرتازه یا معامله‌ی کم"] += 1
            continue
        reasons_all["قابل ارزیابی"] += 1
        t0 = parse(t_sig)
        if t0 is None:
            continue
        hits = hit_table(float(entry), path_after(conn, osym, t0, has_trades))
        eval_rows.append((name, typ, osym, t_sig, float(entry), hits))

    # پوزیشن‌های بسته و باز
    pos = conn.execute(
        """
        WITH b AS (SELECT position_id, MIN(id) AS f, MAX(id) AS l FROM signal_history
                   WHERE position_id IS NOT NULL AND signal_type IN ('BUY_CALL','BUY_PUT') GROUP BY position_id)
        SELECT f.option_symbol, f.time, f.option_price, l.outcome, l.outcome_pct, l.outcome_time
        FROM b JOIN signal_history f ON f.id=b.f JOIN signal_history l ON l.id=b.l
        WHERE f.time>=? ORDER BY f.time""", (START_DATE,)).fetchall()
    # نیمه‌ی اول قفل‌شده برای پوزیشن‌های T1_HIT (بعد از PARTIAL_START)
    partial_map = {}
    for sym, t0s, entry, oc, pct, t_out in pos:
        if oc in CLOSED and entry and float(entry) >= MIN_OPTION_PRICE:
            closed_all.append((name, sym, t0s, float(entry), oc, pct, t_out))
        elif oc in OPEN and entry and float(entry) >= MIN_OPTION_PRICE:
            last = conn.execute(
                "SELECT option_price, time, price_fresh, " + ("trades_count" if has_trades else "NULL") +
                ", volume FROM options WHERE symbol=? AND option_price>=? ORDER BY id DESC LIMIT 1",
                (sym, MIN_OPTION_PRICE)).fetchone()
            if last and fresh_row((last[1], last[0], last[2], last[3], last[4]), has_trades):
                pnl_now = (float(last[0]) / float(entry) - 1) * 100
                if oc == "T1_HIT" and pct is not None and (t_out or "") >= PARTIAL_START:
                    total_now = float(pct) + 0.5 * pnl_now   # نیمه‌ی قفل‌شده + نیمه‌ی باقی‌مانده
                else:
                    total_now = pnl_now
                open_all.append((name, sym, t0s, float(entry), total_now, last[1]))
    conn.close()

n_sig = sum(reasons_all.values())
out(f"\n۱. سیگنال‌های خرید از {START_DATE}: {n_sig}")
for k in ["قابل ارزیابی", "قیمت غیرتازه یا معامله‌ی کم", "قیمت ورود نامعتبر", "قیمت قبل از سیگنال نیست"]:
    c = reasons_all.get(k, 0)
    out(f"   {k:<32} {c:>5}  ({(c / n_sig * 100) if n_sig else 0:5.1f}٪)")

n_eval = len(eval_rows)
out(f"\n۲. نرخ رسیدن به هدف قبل از حد ضرر ۱۵٪ (روی {n_eval} سیگنال قابل ارزیابی)")
if n_eval == 0:
    out("   داده‌ی کافی نیست؛ هنوز سیگنال معتبری در این بازه نیست.")
else:
    for t in TARGETS:
        c = sum(1 for r in eval_rows if r[5][t])
        out(f"   +{t:>3}٪: {c:>4} از {n_eval}  ({c / n_eval * 100:5.1f}٪)")
    if n_eval < 30:
        out(f"   ⚠️ کمتر از ۳۰ سیگنال؛ این عددها هنوز قابل تصمیم‌گیری نیستند.")

out(f"\n۳. پوزیشن‌های بسته (معتبر): {len(closed_all)}")
for name, sym, t0s, entry, oc, pct, t_out in closed_all:
    out(f"   {name} | {sym} | ورود {entry:.0f} ({t0s}) | {oc} | {pct}٪ | خروج {t_out}")
wins = [p for *_, p in [(c[5],) for c in closed_all] if p is not None and p > 0]
if closed_all:
    vals = [c[5] for c in closed_all if c[5] is not None]
    if vals:
        out(f"   میانگین سود/زیان بسته‌ها: {sum(vals) / len(vals):+.1f}٪ | سودده: {len(wins)} از {len(closed_all)}")

out(f"\n   پوزیشن‌های باز با قیمت تازه: {len(open_all)}")
for name, sym, t0s, entry, pnl, t_last in open_all:
    out(f"   {name} | {sym} | ورود {entry:.0f} ({t0s}) | {pnl:+.1f}٪ (قیمت تازه در {t_last})")

out("\n" + "=" * 72)
out("توجه: هیچ‌کدام از اعداد پول واقعی نیستند؛ ارزیابی ربات است.")
out("توجه: تصمیم درباره‌ی ادامه، توقف یا تغییر اهداف با حداقل ۳۰ معامله‌ی معتبر گرفته شود.")
out("=" * 72)

fname = f"weekly_summary_{datetime.now().strftime('%Y-%m-%d')}.txt"
with open(fname, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nخلاصه در فایل {fname} ذخیره شد.")