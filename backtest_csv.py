# -*- coding: utf-8 -*-
"""
بک‌تست ساده‌ی روند + حد سود/ضرر روی داده‌ی روزانه‌ی CSV (فقط خواندنی).

قواعد:
- سیگنال با بسته‌شدن روز t ساخته می‌شه، ورود با باز روز t+1 (بدون نگاه به آینده).
- اگر در یک کندل هم حد ضرر و هم حد سود لمس بشه، ضرر اول فرض می‌شه (محافظه‌کارانه).
- اگر باز شدن روز ورود یا گپ از حد ضرر/سود رد بشه، با قیمت باز همان روز بسته می‌شه.
- در هر لحظه فقط یک معامله‌ی باز داریم.
- نتیجه روی قیمت سهم/ETF است، نه قیمت قرارداد آپشن.
- معاملات بر اساس تاریخ سیگنال به دو دوره تقسیم می‌شن (--split).

اجرا (کنار فایل CSV):
    python backtest_csv.py --csv CharismaAhromi_ETF.csv
    python backtest_csv.py --csv "S_Mellat Bank.csv" --tp 6 --sl 3 --out trades_webmellat.csv
    python backtest_csv.py --csv FILE.csv --split 20240101
خروجی: روی صفحه + فایل معاملات (--out)
"""
import argparse
import csv
import sys
from collections import Counter

EMA_FAST = 20
EMA_SLOW = 50
ADX_PERIOD = 14
ADX_MIN = 25.0
WARMUP = 60          # تا وقتی اندیکاتورها کامل شوند
MIN_TRADES = 30      # حداقل معامله برای قابل‌اتکا بودن


# ---------- خواندن داده ----------
def load(path, date_from):
    rows = []
    reasons = Counter()
    examples = []  # نمونه‌ی ردیف‌های ردشده برای بررسی
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = [h.strip().strip("<>").upper() for h in next(reader)]
        need = ["DTYYYYMMDD", "FIRST", "HIGH", "LOW", "CLOSE", "VOL"]
        for name in need:
            if name not in header:
                sys.exit(f"ستون {name} در فایل پیدا نشد. ستون‌های موجود: {header}")
        ix = {name: header.index(name) for name in need}

        for raw in reader:
            ln = reader.line_num
            if len(raw) < len(header):
                if any(x.strip() for x in raw):
                    reasons["ردیف ناقص"] += 1
                    if len(examples) < 10:
                        examples.append((ln, "ردیف ناقص", raw))
                else:
                    reasons["خط خالی"] += 1
                continue
            try:
                d = raw[ix["DTYYYYMMDD"]].strip()
                o = float(raw[ix["FIRST"]])
                h = float(raw[ix["HIGH"]])
                l = float(raw[ix["LOW"]])
                c = float(raw[ix["CLOSE"]])
                v = float(raw[ix["VOL"]])
            except ValueError:
                reasons["عدد نامعتبر"] += 1
                if len(examples) < 10:
                    examples.append((ln, "عدد نامعتبر", raw))
                continue

            if d < date_from:
                reasons["قبل از تاریخ شروع"] += 1
                continue

            reason = None
            if min(o, h, l, c) <= 0:
                reason = "قیمت صفر یا منفی"
            elif v <= 0:
                reason = "حجم صفر"
            elif not (l <= o <= h and l <= c <= h):
                reason = "OHLC ناسازگار"

            if reason:
                reasons[reason] += 1
                if len(examples) < 10:
                    examples.append((ln, reason, raw))
                continue

            rows.append({"d": d, "o": o, "h": h, "l": l, "c": c, "v": v})

    rows.sort(key=lambda r: r["d"])
    dates = [r["d"] for r in rows]
    dup = len(dates) - len(set(dates))
    if dup:
        reasons["تاریخ تکراری (در داده‌ی نهایی)"] = dup
    return rows, reasons, examples


# ---------- اندیکاتورها ----------
def ema(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    out[n - 1] = e
    for i in range(n, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def macd_hist(c):
    e12 = ema(c, 12)
    e26 = ema(c, 26)
    m = [(a - b) if a is not None and b is not None else None for a, b in zip(e12, e26)]
    start = next((i for i, x in enumerate(m) if x is not None), None)
    hist = [None] * len(c)
    if start is None:
        return hist
    s = ema(m[start:], 9)
    for j, sv in enumerate(s):
        i = start + j
        if sv is not None:
            hist[i] = m[i] - sv
    return hist


def adx_series(h, l, c, n=ADX_PERIOD):
    L = len(c)
    adx = [None] * L
    pdi = [None] * L
    mdi = [None] * L
    tr = [0.0] * L
    pdm = [0.0] * L
    mdm = [0.0] * L
    for i in range(1, L):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    if L <= 2 * n:
        return adx, pdi, mdi

    s_tr = sum(tr[1:n + 1])
    s_p = sum(pdm[1:n + 1])
    s_m = sum(mdm[1:n + 1])
    dx = [None] * L
    for i in range(n, L):
        if i > n:
            s_tr = s_tr - s_tr / n + tr[i]
            s_p = s_p - s_p / n + pdm[i]
            s_m = s_m - s_m / n + mdm[i]
        if s_tr > 0:
            pdi[i] = 100.0 * s_p / s_tr
            mdi[i] = 100.0 * s_m / s_tr
            den = pdi[i] + mdi[i]
            dx[i] = 100.0 * abs(pdi[i] - mdi[i]) / den if den > 0 else 0.0

    start = 2 * n - 1
    adx[start] = sum(dx[n:start + 1]) / n
    for i in range(start + 1, L):
        adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return adx, pdi, mdi


# ---------- سیگنال و شبیه‌سازی ----------
def direction_at(i, ema_f, ema_s, hist, adx, pdi, mdi, c):
    if None in (ema_f[i], ema_s[i], hist[i], adx[i], pdi[i], mdi[i]):
        return None
    if c[i] > ema_f[i] > ema_s[i] and hist[i] > 0 and adx[i] >= ADX_MIN and pdi[i] > mdi[i]:
        return "LONG"
    if c[i] < ema_f[i] < ema_s[i] and hist[i] < 0 and adx[i] >= ADX_MIN and mdi[i] > pdi[i]:
        return "SHORT"
    return None


def simulate(rows, e, side, tp_pct, sl_pct, hold):
    """e = اندیس روز ورود. برمی‌گرداند (نتیجه، اندیس خروج، قیمت خروج، قیمت ورود)."""
    o = [r["o"] for r in rows]
    h = [r["h"] for r in rows]
    l = [r["l"] for r in rows]
    c = [r["c"] for r in rows]
    entry = o[e]
    if side == "LONG":
        tp = entry * (1 + tp_pct / 100)
        sl = entry * (1 - sl_pct / 100)
    else:
        tp = entry * (1 - tp_pct / 100)
        sl = entry * (1 + sl_pct / 100)

    end = min(e + hold, len(rows) - 1)
    for j in range(e, end + 1):
        if side == "LONG":
            if l[j] <= sl:
                return "LOSS", j, min(sl, o[j]), entry
            if h[j] >= tp:
                return "WIN", j, max(tp, o[j]), entry
        else:
            if h[j] >= sl:
                return "LOSS", j, max(sl, o[j]), entry
            if l[j] <= tp:
                return "WIN", j, min(tp, o[j]), entry
    return "TIMEOUT", end, c[end], entry


def run(rows, tp_pct, sl_pct, hold):
    h = [r["h"] for r in rows]
    l = [r["l"] for r in rows]
    c = [r["c"] for r in rows]
    ema_f = ema(c, EMA_FAST)
    ema_s = ema(c, EMA_SLOW)
    hist = macd_hist(c)
    adx, pdi, mdi = adx_series(h, l, c)

    trades = []
    i = WARMUP
    while i < len(rows) - 1:
        side = direction_at(i, ema_f, ema_s, hist, adx, pdi, mdi, c)
        if side is None:
            i += 1
            continue
        e = i + 1
        result, x, exit_p, entry = simulate(rows, e, side, tp_pct, sl_pct, hold)
        sign = 1 if side == "LONG" else -1
        pct = sign * (exit_p / entry - 1) * 100
        trades.append({
            "signal_date": rows[i]["d"],
            "entry_date": rows[e]["d"],
            "side": side,
            "entry": round(entry, 0),
            "exit_date": rows[x]["d"],
            "exit": round(exit_p, 0),
            "result": result,
            "pct": round(pct, 2),
        })
        i = x + 1  # یک معامله در هر لحظه
    return trades


# ---------- گزارش ----------
def report(trades, label):
    print(f"\n--- {label} ---")
    n = len(trades)
    if n == 0:
        print("   معامله‌ای نبود")
        return
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    timeouts = [t for t in trades if t["result"] == "TIMEOUT"]
    pos = [t["pct"] for t in trades if t["pct"] > 0]
    neg = [t["pct"] for t in trades if t["pct"] <= 0]
    avg_w = sum(pos) / len(pos) if pos else 0.0
    avg_l = sum(neg) / len(neg) if neg else 0.0
    ev = sum(t["pct"] for t in trades) / n
    eq = 1.0
    for t in trades:
        eq *= (1 + t["pct"] / 100)

    wr = len(wins) / (len(wins) + len(losses)) * 100 if (len(wins) + len(losses)) else 0.0
    print(f"   معاملات: {n} | WIN: {len(wins)} | LOSS: {len(losses)} | زمان‌اتمام: {len(timeouts)}")
    print(f"   نرخ برد (WIN/(WIN+LOSS)): {wr:.1f}٪")
    print(f"   میانگین سود: {avg_w:.2f}٪ | میانگین زیان: {avg_l:.2f}٪")
    print(f"   امید ریاضی هر معامله (روی قیمت سهم): {ev:.2f}٪")
    print(f"   بازدهی ترکیبی (با سرمایه‌ی کامل در هر معامله): {(eq - 1) * 100:.1f}٪")
    if n < MIN_TRADES:
        print(f"   ⚠️ کمتر از {MIN_TRADES} معامله؛ نتیجه قابل اتکا نیست")


def report_all(trades, title):
    report(trades, f"{title} | همه")
    report([t for t in trades if t["side"] == "LONG"], f"{title} | LONG (شبیه CALL)")
    report([t for t in trades if t["side"] == "SHORT"], f"{title} | SHORT (شبیه PUT)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--from", dest="date_from", default="20220101", help="YYYYMMDD")
    ap.add_argument("--split", default="20240101", help="YYYYMMDD: تقسیم به دو دوره")
    ap.add_argument("--tp", type=float, default=7.0, help="حد سود ٪")
    ap.add_argument("--sl", type=float, default=3.5, help="حد ضرر ٪")
    ap.add_argument("--hold", type=int, default=20, help="حداکثر روز نگهداری")
    ap.add_argument("--out", default="backtest_trades.csv")
    args = ap.parse_args()

    print("=" * 60)
    print("بک‌تست روند + حد سود/ضرر روی داده‌ی روزانه")
    print(f"TP={args.tp}٪ | SL={args.sl}٪ | نگهداری حداکثر={args.hold} روز | از {args.date_from}")
    print("=" * 60)

    rows, reasons, examples = load(args.csv, args.date_from)
    print(f"ردیف‌های معتبر: {len(rows)}")
    if rows:
        print(f"بازه‌ی معتبر: {rows[0]['d']} تا {rows[-1]['d']}")
    print("دلیل رد شدن ردیف‌ها:")
    if not reasons:
        print("   هیچ ردیفی رد نشد")
    for k, v in reasons.most_common():
        print(f"   {k}: {v}")
    if examples:
        print("نمونه‌ی ردیف‌های ردشده (حداکثر ۱۰):")
        for ln, why, raw in examples:
            print(f"   خط {ln} | {why} | {','.join(x.strip() for x in raw)}")

    if len(rows) < WARMUP + 10:
        sys.exit("داده برای بک‌تست کافی نیست")

    trades = run(rows, args.tp, args.sl, args.hold)
    report_all(trades, "کل دوره")

    early = [t for t in trades if t["signal_date"] < args.split]
    late = [t for t in trades if t["signal_date"] >= args.split]
    report_all(early, f"قبل از {args.split}")
    report_all(late, f"از {args.split} به بعد")

    if trades:
        with open(args.out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trades[0].keys()))
            w.writeheader()
            w.writerows(trades)
        print(f"\nجزئیات معاملات در {args.out} ذخیره شد")
    print("\nتوجه: نتیجه روی قیمت سهم/ETF است، نه قیمت قرارداد آپشن. هزینه‌ها لحاظ نشده‌اند.")


if __name__ == "__main__":
    main()