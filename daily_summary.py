# -*- coding: utf-8 -*-
"""
خلاصه‌ی روزانه‌ی ربات در یک فایل JSON کوچک (فقط خواندنی، هیچ داده‌ای تغییر نمی‌کند).

قواعد شمارش (نسخه‌ی اصلاح‌شده):
- هر position_id یک معامله است؛ ردیف‌های تکراری آن شمرده نمی‌شوند.
- «بسته‌شده» فقط WIN / LOSS / BREAK_EVEN است. T1_HIT هنوز باز است.

اجرا (کنار فایل‌های .db پروژه، بعد از بازار):
    python daily_summary.py              -> امروز (اگر قبل از ۶ صبح باشد، روز قبل)
    python daily_summary.py 2026-10-27   -> یک روز مشخص
خروجی: daily_summary_<تاریخ>.json + خلاصه‌ی کوتاه روی صفحه
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

SYMBOLS = [
    ("اهرم", "ahram_v2.db"),
    ("وبملت", "webmellt.db"),
    ("شستا", "shasta.db"),
]
ACTIONABLE = ("BUY_CALL", "BUY_PUT")
CLOSED = ("WIN", "LOSS", "BREAK_EVEN")
OPEN = ("PENDING", "T1_HIT")


def q(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall(), None
    except Exception as e:
        return [], str(e)


def price_block(conn, day):
    rows, err = q(conn, "SELECT time, last_price, volume FROM prices WHERE substr(time,1,10)=? ORDER BY id", (day,))
    if err:
        return {"error": err}
    prices = [r[1] for r in rows if r[1] is not None and r[1] > 0]
    vols = [r[2] for r in rows if r[2] is not None]
    times = [r[0] for r in rows]
    return {
        "rows": len(rows),
        "valid_price_rows": len(prices),
        "open": prices[0] if prices else None,
        "close": prices[-1] if prices else None,
        "high": max(prices) if prices else None,
        "low": min(prices) if prices else None,
        "volume_sum": sum(vols) if vols else None,
        "first_time": times[0] if times else None,
        "last_time": times[-1] if times else None,
        "duplicate_time_rows": len(times) - len(set(times)),
        "invalid_price_rows": len(rows) - len(prices),
    }


def signals_block(conn, day):
    """شمارش سیگنال‌ها: خام (ردیف) و معامله (position)."""
    rows, err = q(
        conn,
        "SELECT time, signal_type, composite_score, option_symbol, option_price, outcome, outcome_pct, position_id "
        "FROM signal_history WHERE substr(time,1,10)=? ORDER BY id",
        (day,),
    )
    if err:
        return {"error": err}
    counts_rows, counts_pos = {}, {}
    trades = {}  # کلید: position_id یا (زمان، نوع، قرارداد) برای ردیف بدون position
    for t, typ, score, opt, opt_price, outcome, pct, pid in rows:
        counts_rows[typ] = counts_rows.get(typ, 0) + 1
        if typ not in ACTIONABLE:
            continue
        key = pid if pid else (t, typ, opt)
        if key not in trades:
            trades[key] = {"time": t, "type": typ, "score": score, "option": opt,
                           "option_price": opt_price, "rows": 0, "position_id": pid}
        trades[key]["rows"] += 1
    counts_pos = {}
    for tr in trades.values():
        counts_pos[tr["type"]] = counts_pos.get(tr["type"], 0) + 1
    return {
        "counts_by_type_rows": counts_rows,
        "counts_by_type_positions": counts_pos,
        "trades_started_today": list(trades.values()),
    }


def closed_block(conn, day):
    """معاملات بسته‌شده‌ای که زمان بسته‌شدنشان امروز است، یک‌بار برای هر position."""
    rows, err = q(
        conn,
        "SELECT s.outcome_time, s.signal_type, s.option_symbol, s.option_price, s.outcome, s.outcome_pct, s.position_id "
        "FROM signal_history s JOIN ("
        "  SELECT position_id, MAX(id) AS mid FROM signal_history "
        "  WHERE outcome IN (?,?,?) AND position_id IS NOT NULL AND substr(outcome_time,1,10)=? "
        "  GROUP BY position_id"
        ") m ON s.id = m.mid ORDER BY s.outcome_time",
        (*CLOSED, day),
    )
    if err:
        return {"error": err}
    return [
        {"time": t, "type": typ, "option": opt, "entry_price": ep, "result": oc, "pct": pct, "position_id": pid}
        for t, typ, opt, ep, oc, pct, pid in rows
    ]


def open_block(conn):
    rows, err = q(
        conn,
        "SELECT sh.position_id, sh.signal_type, sh.option_symbol, sh.option_price, sh.time, m.n, sh.outcome "
        "FROM signal_history sh INNER JOIN ("
        "  SELECT position_id, MIN(id) AS mid, COUNT(*) AS n FROM signal_history "
        "  WHERE outcome IN (?,?) AND position_id IS NOT NULL GROUP BY position_id"
        ") m ON sh.id = m.mid ORDER BY sh.id",
        OPEN,
    )
    if err:
        return {"error": err}
    return [
        {"position_id": pid, "type": typ, "option": opt, "entry_price": ep,
         "entry_time": t, "rows_in_db": n, "status": oc}
        for pid, typ, opt, ep, t, n, oc in rows
    ]


def options_count(conn, day):
    rows, err = q(conn, "SELECT COUNT(*) FROM options WHERE substr(time,1,10)=?", (day,))
    if err:
        return {"error": err}
    return rows[0][0]


def main():
    if len(sys.argv) > 1:
        day = sys.argv[1]
    else:
        now = datetime.now()
        day = (now - timedelta(days=1)).strftime("%Y-%m-%d") if now.hour < 6 else now.strftime("%Y-%m-%d")

    result = {"date": day, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "symbols": {}}
    for name, db in SYMBOLS:
        if not os.path.exists(db):
            result["symbols"][name] = {"error": f"{db} پیدا نشد"}
            continue
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        result["symbols"][name] = {
            "prices": price_block(conn, day),
            "options_rows_today": options_count(conn, day),
            "signals": signals_block(conn, day),
            "closed_today": closed_block(conn, day),
            "open_positions_now": open_block(conn),
        }
        conn.close()

    fname = f"daily_summary_{day}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"خلاصه‌ی روز {day} در فایل {fname} ذخیره شد.")
    print("----- خلاصه‌ی کوتاه برای چت -----")
    print(f"تاریخ: {day}")
    for name, s in result["symbols"].items():
        if "error" in s:
            print(f"{name}: خطا -> {s['error']}")
            continue
        p = s["prices"]
        if "error" in p:
            print(f"{name}: خطای قیمت -> {p['error']}")
            continue
        sig = s["signals"]
        if "error" in sig:
            print(f"{name}: خطای سیگنال -> {sig['error']}")
            continue
        cnt_pos = sig["counts_by_type_positions"]
        closed = s["closed_today"] if isinstance(s["closed_today"], list) else []
        opn = s["open_positions_now"] if isinstance(s["open_positions_now"], list) else []
        print(f"{name}: قیمت باز={p['open']} بسته={p['close']} بالا={p['high']} پایین={p['low']} | ردیف={p['rows']}")
        print(f"  معامله‌ی شروع‌شده امروز (هر position یک‌بار): {cnt_pos} | بسته‌شده: {len(closed)} | باز: {len(opn)}")
        for t in sig["trades_started_today"][:5]:
            print(f"  - {str(t['time'])[11:16]} {t['type']} امتیاز={t['score']} ردیف={t['rows']}")
    print("----- پایان -----")


if __name__ == "__main__":
    main()