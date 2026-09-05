# -*- coding: utf-8 -*-
"""
موتور بک‌تست تحلیلی ماتریسی نوسان‌گیری آپشن (Matrix Swing Backtester)
نسخه نهایی 2026-09-05 - با خواندن مستقیم ستون واقعی composite_score
تحلیل تاثیر فیلتر کیفیت در سطوح امتیازی 0، 55، 60 و 65
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logging.basicConfig(level=logging.WARNING)  # جلوگیری از شلوغی ترمینال
logger = logging.getLogger("Backtester")

DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db"
}

SETTINGS = {
    "اهرم": {"tp": 7.0, "sl": 3.5, "max_hold": 210},
    "وبملت": {"tp": 6.0, "sl": 3.0, "max_hold": 210},
    "شستا": {"tp": 6.0, "sl": 3.0, "max_hold": 210}
}


def parse_dt(dt_str: str) -> Optional[datetime]:
    if not dt_str or dt_str == "-":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(dt_str).strip(), fmt)
        except ValueError:
            continue
    return None


def run_single_backtest(db_path: str, symbol: str, min_score: float) -> Dict[str, Any]:
    cfg = SETTINGS.get(symbol, {"tp": 6.0, "sl": 3.0, "max_hold": 210})
    TP_PCT = cfg["tp"]
    SL_PCT = cfg["sl"]
    MAX_HOLD = cfg["max_hold"]

    res = {
        "min_score": min_score,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "profit_pct": 0.0
    }

    if not os.path.exists(db_path):
        return res

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()

    try:
        # ۱. لود قیمت‌ها
        cur.execute("SELECT time, last_price, closing_price FROM prices ORDER BY id ASC")
        prices = []
        for r in cur.fetchall():
            dt = parse_dt(r[0])
            p = float(r[1] or r[2] or 0)
            if dt and p > 0:
                prices.append({"dt": dt, "price": p})

        if len(prices) < 10:
            return res

        # ۲. لود سیگنال‌ها با ستون واقعی composite_score
        cur.execute("SELECT time, signal_type, composite_score FROM signal_history ORDER BY id ASC")
        signals = cur.fetchall()

        gross_profit = 0.0
        gross_loss = 0.0

        for sig in signals:
            sig_dt = parse_dt(sig[0])
            sig_type = str(sig[1] or "").upper().strip()
            
            try:
                score = float(sig[2]) if sig[2] is not None else 0.0
            except (ValueError, TypeError):
                score = 0.0

            if not sig_dt or "WATCH" in sig_type or "NEUTRAL" in sig_type:
                continue

            # اعمال فیلتر واقعی امتیاز composite_score
            if score < min_score:
                continue

            is_call = "CALL" in sig_type or "BUY" in sig_type or "خرید" in sig_type
            is_put = "PUT" in sig_type or "فروش" in sig_type

            if not is_call and not is_put:
                continue

            # پیدا کردن نقطه ورود
            entry_p = None
            entry_idx = None
            for idx, p in enumerate(prices):
                if p["dt"] >= sig_dt:
                    entry_p = p["price"]
                    entry_idx = idx
                    break

            if entry_p is None or entry_idx is None:
                continue

            res["trades"] += 1

            if is_call:
                tp_p = entry_p * (1 + (TP_PCT / 100))
                sl_p = entry_p * (1 - (SL_PCT / 100))
            else:
                tp_p = entry_p * (1 - (TP_PCT / 100))
                sl_p = entry_p * (1 + (SL_PCT / 100))

            trade_res = "EXPIRED"
            end_idx = min(entry_idx + MAX_HOLD, len(prices))

            for p in prices[entry_idx + 1: end_idx]:
                cur_p = p["price"]
                if is_call:
                    if cur_p >= tp_p:
                        trade_res = "WIN"
                        break
                    elif cur_p <= sl_p:
                        trade_res = "LOSS"
                        break
                else:
                    if cur_p <= tp_p:
                        trade_res = "WIN"
                        break
                    elif cur_p >= sl_p:
                        trade_res = "LOSS"
                        break

            if trade_res == "WIN":
                res["wins"] += 1
                gross_profit += (TP_PCT * 6)
            elif trade_res == "LOSS":
                res["losses"] += 1
                gross_loss += (SL_PCT * 6)

        closed = res["wins"] + res["losses"]
        if closed > 0:
            res["win_rate"] = (res["wins"] / closed) * 100
            res["profit_pct"] = gross_profit - gross_loss

    except Exception as e:
        print(f"خطا در {symbol}: {e}")
    finally:
        conn.close()

    return res


def main():
    print("\n" + "="*80)
    print("📊 ماتریس مقایسه‌ای بک‌تست نوسان‌گیری با فیلترهای مختلف امتیاز (composite_score)")
    print("================================================================================")
    
    thresholds = [0.0, 55.0, 60.0, 65.0]

    for sym, db in DBS.items():
        print(f"\n🔹 نماد: [{sym}]")
        print(f"{'حداقل امتیاز':<14} | {'معاملات':<10} | {'برد / باخت':<12} | {'وین‌ریت':<10} | {'بازدهی اهرمی':<15}")
        print("-" * 70)
        
        for th in thresholds:
            r = run_single_backtest(db, sym, th)
            label = "همه (بدون فیلتر)" if th == 0 else f"امتیاز >= {th:.0f}"
            wl = f"{r['wins']} / {r['losses']}"
            wr = f"{r['win_rate']:.1f}%" if r['trades'] > 0 else "-"
            prof = f"+{r['profit_pct']:.1f}%" if r['profit_pct'] >= 0 else f"{r['profit_pct']:.1f}%"
            
            print(f"{label:<14} | {r['trades']:<10} | {wl:<12} | {wr:<10} | {prof:<15}")

    print("\n" + "="*80)
    print("💡 تحلیل نتایج: کاهش تعداد معاملات نشان‌دهنده حذف سیگنال‌های کم‌کیفیت است.")
    print("================================================================================\n")


if __name__ == "__main__":
    main()