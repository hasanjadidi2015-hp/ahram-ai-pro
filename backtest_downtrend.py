# -*- coding: utf-8 -*-
"""
بک‌تست تعریف «ریزش کامل» برای خرید پوت (SHORT) روی داده‌ی روزانه‌ی CSV (فقط خواندنی).

شش شرط (همه باید برقرار باشند):
 1. بسته زیر EMA20 و EMA50
 2. EMA20 زیر EMA50 و شیب EMA20 منفی
 3. هیستوگرام MACD منفی و از ۳ کندل قبل پایین‌تر
 4. ADX >= 25 و -DI بالاتر از +DI
 5. بسته زیر کف دو روز قبل
 6. قیمت خارج از زون ممنوعه‌ی فیبو (تقریب: ۳۸.۲٪ تا ۶۱.۸٪ دامنه‌ی ۲۰ روز اخیر)

مقایسه با قانون SHORT قبلی (backtest_csv) روی همان داده و همان تنظیم TP/SL.
قواعد ورود/خروج مثل backtest_csv: ورود با باز روز بعد، یک معامله هم‌زمان، ضرر اول در کندل مشترک.

اجرا (کنار backtest_csv.py و فایل CSV):
    python backtest_downtrend.py --csv CharismaAhromi_ETF.csv --tp 7 --sl 3.5 --split 20240101
"""
import argparse
import sys

import backtest_csv as bc


def fib_zone_ok(i, c, h, l, n=20):
    """True اگر قیمت خارج از زون ۳۸.۲٪ تا ۶۱.۸٪ دامنه‌ی n کندل اخیر باشد. تقریب است."""
    if i < n:
        return False
    hi = max(h[i - n + 1:i + 1])
    lo = min(l[i - n + 1:i + 1])
    rng = hi - lo
    if rng <= 0:
        return False
    z_low = lo + 0.382 * rng
    z_high = lo + 0.618 * rng
    return not (z_low <= c[i] <= z_high)


def full_downtrend(i, ema_f, ema_s, hist, adx, pdi, mdi, o, h, l, c):
    """خروجی: (bool, dict جزئیات شروط)."""
    need = (ema_f[i], ema_s[i], ema_f[i - 1], hist[i], hist[i - 3] if i >= 3 else None,
            adx[i], pdi[i], mdi[i])
    if i < 3 or None in need:
        return False, {}
    cond = {
        "1_زیر_EMA20_و_EMA50": c[i] < ema_f[i] and c[i] < ema_s[i],
        "2_EMA20_زیر_EMA50_و_شیب_منفی": ema_f[i] < ema_s[i] and ema_f[i] < ema_f[i - 1],
        "3_MACD_منفی_و_پایین‌تر_از_۳_کندل_قبل": hist[i] < 0 and hist[i] < hist[i - 3],
        "4_ADX_قوی_و_-DI_بالاتر": adx[i] >= 25 and mdi[i] > pdi[i],
        "5_شکست_کف_دو_روز_قبل": c[i] < min(l[i - 1], l[i - 2]),
        "6_خارج_از_زون_فیبو": fib_zone_ok(i, c, h, l),
    }
    return all(cond.values()), cond


def run_full(rows, tp, sl, hold):
    o = [r["o"] for r in rows]
    h = [r["h"] for r in rows]
    l = [r["l"] for r in rows]
    c = [r["c"] for r in rows]
    ema_f = bc.ema(c, bc.EMA_FAST)
    ema_s = bc.ema(c, bc.EMA_SLOW)
    hist = bc.macd_hist(c)
    adx, pdi, mdi = bc.adx_series(h, l, c)
    trades = []
    i = bc.WARMUP
    while i < len(rows) - 1:
        ok, _ = full_downtrend(i, ema_f, ema_s, hist, adx, pdi, mdi, o, h, l, c)
        if not ok:
            i += 1
            continue
        e = i + 1
        result, x, exit_p, entry = bc.simulate(rows, e, "SHORT", tp, sl, hold)
        pct = -(exit_p / entry - 1) * 100
        trades.append({"signal_date": rows[i]["d"], "entry_date": rows[e]["d"], "side": "SHORT",
                       "entry": round(entry, 0), "exit_date": rows[x]["d"], "exit": round(exit_p, 0),
                       "result": result, "pct": round(pct, 2)})
        i = x + 1
    return trades


def summary(trades, label):
    n = len(trades)
    if n == 0:
        print(f"   [{label}] معامله‌ای نبود")
        return
    pcts = [t["pct"] for t in trades]
    wins = [p for p in pcts if p > 0]
    losses = [p for p in pcts if p <= 0]
    ev = sum(pcts) / n
    eq = 1.0
    for p in pcts:
        eq *= (1 + p / 100)
    wr = len(wins) / n * 100
    print(f"   [{label}] معامله: {n} | سودده: {len(wins)} | زیان‌ده: {len(losses)} | نرخ برد: {wr:.1f}٪ | "
          f"امید ریاضی: {ev:+.2f}٪ | بازدهی ترکیبی: {(eq - 1) * 100:+.1f}٪")
    if n < bc.MIN_TRADES:
        print(f"      ⚠️ کمتر از {bc.MIN_TRADES} معامله؛ نتیجه قابل اتکا نیست")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--from", dest="date_from", default="20220101")
    ap.add_argument("--split", default="20240101")
    ap.add_argument("--tp", type=float, default=7.0)
    ap.add_argument("--sl", type=float, default=3.5)
    ap.add_argument("--hold", type=int, default=20)
    args = ap.parse_args()

    rows, reasons, _ = bc.load(args.csv, args.date_from)
    if len(rows) < bc.WARMUP + 10:
        sys.exit("داده کافی نیست")

    full = run_full(rows, args.tp, args.sl, args.hold)
    old = [t for t in bc.run(rows, args.tp, args.sl, args.hold) if t["side"] == "SHORT"]

    print("=" * 70)
    print(f"پوت با «ریزش کامل» (۶ شرط) | TP={args.tp}٪ SL={args.sl}٪ نگهداری={args.hold} روز")
    summary(full, "کل دوره")
    summary([t for t in full if t["signal_date"] < args.split], f"قبل از {args.split}")
    summary([t for t in full if t["signal_date"] >= args.split], f"از {args.split} به بعد")
    print("-" * 70)
    print("پوت با قانون قبلی (EMA+MACD+ADX بدون شروط ریزش کامل)")
    summary(old, "کل دوره")
    summary([t for t in old if t["signal_date"] < args.split], f"قبل از {args.split}")
    summary([t for t in old if t["signal_date"] >= args.split], f"از {args.split} به بعد")
    print("-" * 70)
    print("توجه: شرط ۶ (فیبو) تقریبی است. نتیجه روی قیمت سهم/ETF است، نه آپشن.")


if __name__ == "__main__":
    main()