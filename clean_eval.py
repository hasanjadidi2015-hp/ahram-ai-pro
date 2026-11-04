# -*- coding: utf-8 -*-
"""
ارزیاب تمیز نتایج ربات -- فقط خواندنی، هیچ دیتابیسی را تغییر نمی‌دهد.

قواعد شمارش (هر کدام با دلیل مشخص):
  1. فقط پوزیشن‌هایی که ورودشان از START_DATE به بعد است.
  2. هر position_id یک معامله است (ورود از اولین ردیف، وضعیت از آخرین ردیف).
  3. قیمت ورود باید >= MIN_OPTION_PRICE باشد. قیمت‌های ۱ یا ۲ ریالی واقعی نیستند.
  4. پوزیشن NO_TRADE از ارزیابی بیرون است (با دلیل جدا نشان داده می‌شود).
  5. بسته‌شده (WIN/LOSS/BREAK_EVEN) فقط وقتی معتبر است که در لحظه‌ی خروج حداقل
     MIN_EXIT_TRADES معامله‌ی امروز ثبت شده باشد. خروج بی‌معامله (مثل ۱۷۰٪ طملت9041) حذف می‌شود.
  6. باز (PENDING/T1_HIT) فقط وقتی ارزیابی می‌شود که آخرین قیمت آن تازه و معتبر باشد.
     سود/زیان باز = آخرین قیمت معتبر نسبت به ورود، و فقط نشان داده می‌شود، جدا از عدد بسته.

اجرا (کنار فایل‌های .db):
    python clean_eval.py
"""
import os
import sqlite3
from collections import Counter

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-10-17"
PARTIAL_EXIT_START = "2026-11-04 00:00:00"  # همان مقدار ahram_pro.py
MIN_OPTION_PRICE = 10.0
MIN_EXIT_TRADES = 5
MIN_SAMPLE = 30

POS_SQL = """
WITH b AS (
  SELECT position_id, MIN(id) AS first_id, MAX(id) AS last_id
  FROM signal_history WHERE position_id IS NOT NULL AND signal_type IN ('BUY_CALL','BUY_PUT')
  GROUP BY position_id)
SELECT b.position_id, f.time, f.option_price, f.option_symbol, l.outcome, l.outcome_pct, l.outcome_time, l.signal_type, l.outcome_time
FROM b JOIN signal_history f ON f.id = b.first_id JOIN signal_history l ON l.id = b.last_id
WHERE f.time >= ? ORDER BY f.time
"""


def last_fresh_price(conn, sym, before=None):
    q = ("SELECT time, option_price, trades_count, volume FROM options "
         "WHERE symbol=? AND option_price>=? AND price_fresh=1")
    args = [sym, MIN_OPTION_PRICE]
    if before:
        q += " AND time<=?"
        args.append(before)
    q += " ORDER BY id DESC LIMIT 1"
    return conn.execute(q, args).fetchone()


def exit_trades_ok(conn, sym, t_out):
    """آیا در لحظه‌ی خروج معامله‌ی کافی ثبت شده؟ (از آخرین ردیف قبل از خروج)"""
    row = conn.execute(
        "SELECT trades_count, volume FROM options WHERE symbol=? AND time<=? ORDER BY id DESC LIMIT 1",
        (sym, t_out or "9999"),
    ).fetchone()
    if not row:
        return False, "هیچ قیمتی در لحظه‌ی خروج ثبت نشده"
    if row[0] is None:
        # ستون تعداد معامله قبلاً وجود نداشت؛ یعنی نمی‌دانیم معامله بوده یا نه
        return False, "داده‌ی تعداد معامله در لحظه‌ی خروج ثبت نشده (خروج قدیمی، قابل تأیید نیست)"
    trades = row[0]
    if trades < MIN_EXIT_TRADES:
        return False, f"خروج بی‌معامله (تعداد معامله‌ی لحظه‌ی خروج: {trades:.0f})"
    return True, ""


closed_pcts, open_items, excluded = [], [], []
seen_dup = 0

print("=" * 70)
print(f"ارزیاب تمیز نتایج | از {START_DATE} | حداقل قیمت ورود {MIN_OPTION_PRICE} ریال")
print("=" * 70)

for name, db in DBS:
    if not os.path.exists(db):
        print(f"\n{name}: {db} پیدا نشد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(POS_SQL, (START_DATE,)).fetchall()
    reasons = Counter()
    closed_here, open_here = [], []
    for pid, t0, entry, sym, outcome, pct, t_out, sig, t_t1 in rows:
        if outcome == "NO_TRADE":
            reasons["بی‌معامله (NO_TRADE)"] += 1
            excluded.append((name, sym, t0, "بی‌معامله (NO_TRADE)"))
            continue
        if entry is None or float(entry) < MIN_OPTION_PRICE:
            reasons[f"قیمت ورود نامعتبر (<{MIN_OPTION_PRICE:.0f} ریال)"] += 1
            excluded.append((name, sym, t0, f"قیمت ورود {entry} نامعتبر"))
            continue
        entry = float(entry)
        if outcome in ("WIN", "LOSS", "BREAK_EVEN"):
            ok, why = exit_trades_ok(conn, sym, t_out)
            if not ok:
                reasons["خروج بی‌معامله یا بدون داده‌ی معامله"] += 1
                excluded.append((name, sym, t0, why))
                continue
            if pct is None:
                reasons["درصد خروج ثبت نشده"] += 1
                continue
            closed_here.append((sym, entry, float(pct), outcome, t_out))
        elif outcome in ("PENDING", "T1_HIT"):
            lp = last_fresh_price(conn, sym)
            if not lp:
                reasons["باز بدون قیمت تازه (ارزیابی نشد)"] += 1
                excluded.append((name, sym, t0, "باز، بدون قیمت تازه"))
                continue
            pnl_now = (float(lp[1]) / entry - 1) * 100
            if outcome == "T1_HIT" and pct is not None and (t_t1 or "") >= PARTIAL_EXIT_START:
                # نیمه‌ی اول در هدف اول بسته و سودش قفل شده؛ نیمه‌ی باقی‌مانده با قیمت فعلی
                total_now = float(pct) + 0.5 * pnl_now
            else:
                total_now = pnl_now
            open_here.append((sym, entry, total_now, outcome, lp[0]))
        else:
            reasons[f"وضعیت ناشناخته ({outcome})"] += 1
    conn.close()

    closed_pcts.extend(closed_here)
    open_items.extend(open_here)
    print(f"\n--- {name} ({db}) ---")
    print(f"   بسته‌ی معتبر: {len(closed_here)} | باز با قیمت تازه: {len(open_here)}")
    for k, v in reasons.most_common():
        print(f"   کنار گذاشته شد — {k}: {v}")
    for sym, entry, pct, oc, t in closed_here:
        print(f"      بسته  {sym} | ورود {entry:.0f} | {oc} | {pct:+.1f}٪ | خروج {t}")
    for sym, entry, pct, oc, t in open_here:
        print(f"      باز   {sym} | ورود {entry:.0f} | {pct:+.1f}٪ (قیمت تازه در {t})")

def stats(vals):
    n = len(vals)
    if n == 0:
        return None
    w = [v for v in vals if v > 0]
    l = [v for v in vals if v <= 0]
    eq = 1.0
    for v in vals:
        eq *= 1 + v / 100
    return dict(n=n, wins=len(w), wr=len(w) / n * 100,
                avg_w=(sum(w) / len(w)) if w else 0.0, avg_l=(sum(l) / len(l)) if l else 0.0,
                ev=sum(vals) / n, comp=(eq - 1) * 100)

print("\n" + "=" * 70)
s_closed = stats([p for _, _, p, _, _ in closed_pcts])
s_all = stats([p for _, _, p, _, _ in closed_pcts] + [p for _, _, p, _, _ in open_items])

def show(label, s):
    if not s:
        print(f"{label}: معامله‌ای نیست")
        return
    print(f"{label}: {s['n']} معامله | سودده {s['wins']} ({s['wr']:.0f}٪)")
    print(f"   میانگین سود {s['avg_w']:.1f}٪ | میانگین زیان {s['avg_l']:.1f}٪")
    print(f"   امید ریاضی هر معامله {s['ev']:+.2f}٪ | بازدهی ترکیبی {s['comp']:+.1f}٪")
    if s["n"] < MIN_SAMPLE:
        print(f"   ⚠️ کمتر از {MIN_SAMPLE} معامله؛ هنوز برای تصمیم کافی نیست")

show("فقط بسته‌های معتبر", s_closed)
show("بسته + باز با قیمت تازه", s_all)
print("=" * 70)
print("کنار گذاشته‌شده‌ها (با دلیل):")
for name, sym, t0, why in excluded:
    print(f"   {name} | {sym} | ورود {t0} | {why}")
print("=" * 70)