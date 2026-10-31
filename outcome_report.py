# -*- coding: utf-8 -*-
"""
گزارش نتایج معاملات -- فقط خواندنی، هیچ چیزی را تغییر نمی‌دهد.

دو عدد جدا می‌دهد:
  A) فقط پوزیشن‌های بسته‌شده (WIN / LOSS / BREAK_EVEN)
  B) همه‌ی پوزیشن‌ها: بسته‌شده‌ها + باز (PENDING / T1_HIT)

قواعد:
- فقط پوزیشن‌هایی که ورودشان از START_DATE به بعد است شمرده می‌شوند.
- هر position_id یک معامله است: ورود از اولین ردیف، وضعیت از آخرین ردیف.
- قیمت باز از جدول options (آخرین قیمت مثبت همان قرارداد) خوانده می‌شود، نه از signal_history.
- اگر قیمت باز نداشته باشد یا قدیمی‌تر از STALE_MINUTES باشد، پوزیشن جدا گزارش و از عدد B کنار گذاشته می‌شود.
- INCONCLUSIVE و داده‌ی قدیمی شمرده نمی‌شوند.

اجرا (کنار فایل‌های .db):
    python outcome_report.py
خروجی روی صفحه + outcome_report.txt
"""
import os
import sqlite3
from datetime import datetime

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-10-17"   # ۲۵ مهر ۱۴۰۵
STALE_MINUTES = 60          # قیمت آخر قدیمی‌تر از این = مشکوک
MIN_TRADES = 30
OUT = "outcome_report.txt"
CLOSED = ("WIN", "LOSS", "BREAK_EVEN")
OPEN = ("PENDING", "T1_HIT")

POSITIONS_SQL = """
WITH bounds AS (
    SELECT position_id, MIN(id) AS first_id, MAX(id) AS last_id
    FROM signal_history
    WHERE position_id IS NOT NULL AND signal_type IN ('BUY_CALL', 'BUY_PUT')
    GROUP BY position_id
)
SELECT b.position_id, f.time, f.option_price, l.option_symbol, l.outcome, l.outcome_pct
FROM bounds b
JOIN signal_history f ON f.id = b.first_id
JOIN signal_history l ON l.id = b.last_id
WHERE f.time >= ?
ORDER BY f.time
"""

lines = []


def out(s=""):
    print(s)
    lines.append(str(s))


def latest_option_price(conn, symbol):
    """آخرین قیمت مثبت قرارداد از جدول options: (زمان، قیمت) یا None"""
    if not symbol:
        return None
    row = conn.execute(
        "SELECT time, option_price FROM options "
        "WHERE symbol = ? AND option_price > 0 ORDER BY id DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    return row if row else None


def parse_ts(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def age_minutes(newest, ts):
    """فاصله‌ی ts تا جدیدترین ثبت options همان دیتابیس (دقیقه). None اگر نامعتبر."""
    a, b = parse_ts(newest), parse_ts(ts)
    if a is None or b is None:
        return None
    return (a - b).total_seconds() / 60


def newest_options_time(conn):
    row = conn.execute("SELECT MAX(time) FROM options").fetchone()
    return row[0] if row and row[0] else None


def pct_of(entry, last):
    if entry and last and entry > 0 and last > 0:
        return (last / entry - 1) * 100
    return None


def stats(pcts):
    n = len(pcts)
    wins = [p for p in pcts if p > 0]
    losses = [p for p in pcts if p <= 0]
    s = {"n": n, "wins": len(wins), "losses": len(losses),
         "wr": (len(wins) / n * 100) if n else 0.0,
         "avg_w": (sum(wins) / len(wins)) if wins else 0.0,
         "avg_l": (sum(losses) / len(losses)) if losses else 0.0,
         "ev": (sum(pcts) / n) if n else 0.0}
    eq = 1.0
    for p in pcts:
        eq *= (1 + p / 100)
    s["compound"] = (eq - 1) * 100
    return s


def print_stats(label, s):
    out(f"   [{label}] معاملات: {s['n']} | سودده: {s['wins']} | زیان‌ده: {s['losses']} | نرخ برد: {s['wr']:.1f}٪")
    if s["n"]:
        out(f"      میانگین سود: {s['avg_w']:.2f}٪ | میانگین زیان: {s['avg_l']:.2f}٪")
        out(f"      امید ریاضی هر معامله: {s['ev']:.2f}٪ | بازدهی ترکیبی: {s['compound']:.1f}٪")
    if s["n"] < MIN_TRADES:
        out(f"      ⚠️ کمتر از {MIN_TRADES} معامله؛ قابل اتکا نیست")


closed_all, open_all, open_detail, problems = [], [], [], []

out("=" * 70)
out(f"گزارش نتایج معاملات (فقط خواندنی) -- از {START_DATE} به بعد")
out("=" * 70)

for name, db in DBS:
    if not os.path.exists(db):
        out(f"\n⚠️ {db} پیدا نشد -- رد شد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(POSITIONS_SQL, (START_DATE,)).fetchall()
        closed_pcts, open_pcts = [], []
        n_skip = 0
        newest = newest_options_time(conn)
        for pid, t0, entry, symbol, outcome, outcome_pct in rows:
            if outcome in CLOSED:
                lp_closed = latest_option_price(conn, symbol)
                pct = outcome_pct if outcome_pct is not None else pct_of(entry, lp_closed[1] if lp_closed else None)
                if pct is None:
                    problems.append(f"{name} | {symbol} | ورود {t0} | بسته‌شده ولی درصد ندارد")
                    n_skip += 1
                    continue
                closed_pcts.append(pct)
            elif outcome in OPEN:
                lp = latest_option_price(conn, symbol)
                if lp is None:
                    problems.append(f"{name} | {symbol} | ورود {t0} | قیمت مثبتی در options پیدا نشد")
                    n_skip += 1
                    continue
                age = age_minutes(newest, lp[0])
                pct = pct_of(entry, lp[1])
                if pct is None:
                    problems.append(f"{name} | {symbol} | ورود {t0} | قیمت ورود نامعتبر")
                    n_skip += 1
                    continue
                if age is None or age > STALE_MINUTES:  # age = فاصله تا جدیدترین ثبت
                    problems.append(f"{name} | {symbol} | آخرین قیمت {lp[0]} قدیمی است")
                    open_detail.append((name, symbol, t0, entry, lp, pct, outcome, True))
                    continue
                open_pcts.append(pct)
                open_detail.append((name, symbol, t0, entry, lp, pct, outcome, False))
            else:
                n_skip += 1

        out(f"\n--- {name} ({db}) ---")
        out(f"   پوزیشن‌های یافت‌شده: {len(rows)} | بسته: {len(closed_pcts)} | "
            f"باز با قیمت تازه: {len(open_pcts)} | رد/مشکوک: {n_skip}")
        print_stats("فقط بسته‌شده", stats(closed_pcts))
        print_stats("بسته + باز تازه", stats(closed_pcts + open_pcts))
        closed_all.extend(closed_pcts)
        open_all.extend(open_pcts)
    finally:
        conn.close()

out("\n" + "=" * 70)
out("جمع کل همه‌ی نمادها:")
print_stats("فقط بسته‌شده", stats(closed_all))
print_stats("بسته + باز تازه", stats(closed_all + open_all))

if open_detail:
    out("\nپوزیشن‌های باز:")
    for name, sym, t0, entry, lp, pct, outcome, stale in open_detail:
        flag = []
        if outcome == "T1_HIT":
            flag.append("به هدف ۱ رسیده")
        if stale:
            flag.append("قیمت قدیمی، خارج از شمارش")
        extra = f" [{'، '.join(flag)}]" if flag else ""
        out(f"   {name} | {sym} | ورود {t0} ({entry}) | آخرین {lp[1]} در {lp[0]} | {pct:+.1f}٪{extra}")

if problems:
    out("\nموارد مشکوک یا ناقص:")
    for p in problems:
        out(f"   - {p}")

out("\nتوجه: INCONCLUSIVE و داده‌ی قدیمی شمرده نشده‌اند.")
out(f"توجه: تازگی قیمت نسبت به جدیدترین ثبت options همان دیتابیس سنجیده می‌شود (آستانه {STALE_MINUTES} دقیقه).")
out("توجه: هیچ‌کدام از اعداد پول واقعی نیستند؛ ارزیابی ربات است.")
out("=" * 70)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nنتیجه در فایل {OUT} ذخیره شد.")