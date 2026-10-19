# -*- coding: utf-8 -*-
"""
خلاصه‌ی روزانه‌ی رباط در یک فایل JSON کوچک (فقط خواندنی، هیچ داده‌ای تغییر نمی‌کنه).

اجرا (کنار فایل‌های .db پروژه، بعد از بازار):
    python daily_summary.py              -> خلاصه‌ی امروز
    python daily_summary.py 2026-10-19   -> خلاصه‌ی یک روز مشخص

خروجی: daily_summary_<تاریخ>.json
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

SYMBOLS = [
    ("اهرم", "ahram_v2.db"),
    ("وبملت", "webmellt.db"),
    ("شستا", "shasta.db"),
]
ACTIONABLE = ("BUY_CALL", "BUY_PUT")
CLOSED = ("WIN", "LOSS", "BREAK_EVEN", "T1_HIT")


def q(conn, sql, args=()):
    """اجرای امن کوئری. اگه خطا بود، خطا رو صریح برمی‌گردونه (نه سکوت)."""
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
    block = {
        "rows": len(rows),
        "valid_price_rows": len(prices),
        "open": prices[0] if prices else None,
        "close": prices[-1] if prices else None,
        "high": max(prices) if prices else None,
        "low": min(prices) if prices else None,
        "volume_sum": sum(vols) if vols else None,
        "volume_max_single": max(vols) if vols else None,
        "first_time": times[0] if times else None,
        "last_time": times[-1] if times else None,
    }
    # هشدار کیفیت: زمان تکراری یا قیمت نامعتبر
    block["duplicate_time_rows"] = len(times) - len(set(times))
    block["invalid_price_rows"] = len(rows) - len(prices)
    return block


def signals_block(conn, day):
    rows, err = q(
        conn,
        "SELECT time, signal_type, composite_score, option_symbol, option_price, outcome, outcome_pct "
        "FROM signal_history WHERE substr(time,1,10)=? ORDER BY id",
        (day,),
    )
    if err:
        return {"error": err}
    counts = {}
    actionable = []
    for t, typ, score, opt, opt_price, outcome, pct in rows:
        counts[typ] = counts.get(typ, 0) + 1
        if typ in ACTIONABLE:
            actionable.append({
                "time": t, "type": typ, "score": score, "option": opt,
                "option_price": opt_price, "outcome": outcome, "outcome_pct": pct,
            })
    return {"counts_by_type": counts, "actionable": actionable}


def closed_block(conn, day):
    rows, err = q(
        conn,
        "SELECT outcome_time, signal_type, option_symbol, option_price, outcome, outcome_pct "
        "FROM signal_history WHERE outcome IN (?,?,?,?) AND substr(outcome_time,1,10)=? ORDER BY id",
        (*CLOSED, day),
    )
    if err:
        return {"error": err}
    return [
        {"time": t, "type": typ, "option": opt, "entry_price": ep, "result": oc, "pct": pct}
        for t, typ, opt, ep, oc, pct in rows
    ]


def open_block(conn):
    # هر position_id یک پوزیشن است؛ ردیف‌های تکراری همون پوزیشن (ثبت‌های بعدی) حذف می‌شن
    rows, err = q(
        conn,
        "SELECT sh.position_id, sh.signal_type, sh.option_symbol, sh.option_price, sh.time, m.n "
        "FROM signal_history sh INNER JOIN ("
        "  SELECT position_id, MIN(id) AS mid, COUNT(*) AS n FROM signal_history "
        "  WHERE outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL GROUP BY position_id"
        ") m ON sh.id = m.mid ORDER BY sh.id",
    )
    if err:
        return {"error": err}
    return [
        {"position_id": pid, "type": typ, "option": opt, "entry_price": ep, "entry_time": t, "rows_in_db": n}
        for pid, typ, opt, ep, t, n in rows
    ]


def options_count(conn, day):
    rows, err = q(conn, "SELECT COUNT(*) FROM options WHERE substr(time,1,10)=?", (day,))
    if err:
        return {"error": err}
    return rows[0][0]


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
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
    print("فایل رو آپلود کن یا محتواش رو بفرست (حجمش کمه).")


if __name__ == "__main__":
    main()