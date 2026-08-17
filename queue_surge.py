# -*- coding: utf-8 -*-
"""
تشخیص صف خرید/فروش سنگین - نسخه نهایی
"""
import sqlite3
from datetime import datetime, time as dtime
import config

MARKET_OPEN = dtime(9, 0)
MARKET_CLOSE = dtime(12, 30)
TOTAL_MARKET_MINUTES = (12 * 60 + 30) - (9 * 60)

CEILING_GAP_MIN = 1.5
HEAVY_RATIO_MIN = 1.5


def compute_avg_daily_volume(days=20):
    try:
        conn = sqlite3.connect(config.DATABASE_NAME)
        cur = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")
        cur.execute(
            "SELECT substr(time,1,10) AS d, MAX(volume) AS v FROM prices "
            "WHERE volume IS NOT NULL AND volume > 0 AND substr(time,1,10) != ? "
            "GROUP BY d ORDER BY d DESC LIMIT ?",
            (today_str, days + 2)
        )
        rows = [float(r[1]) for r in cur.fetchall() if r[1] and float(r[1]) > 0]
        conn.close()
        if len(rows) < 5:
            return None
        rows.sort()
        trimmed = rows[1:-1] if len(rows) >= 6 else rows
        return sum(trimmed) / len(trimmed)
    except:
        return None


def _minutes_since_open():
    now = datetime.now()
    m = (now.hour * 60 + now.minute) - (MARKET_OPEN.hour * 60 + MARKET_OPEN.minute)
    return max(1, min(TOTAL_MARKET_MINUTES, m))


def detect_heavy_queue(current_price, yesterday_close, today_volume, avg_daily_volume=None):
    result = {
        "queue_type": None,
        "gap_pct": 0.0,
        "heaviness": 0.0,
        "locked": False,
        "heavy": False,
        "reason": "-"
    }

    if not yesterday_close or yesterday_close <= 0 or not current_price or current_price <= 0:
        result["reason"] = "no price data"
        return result

    gap = (current_price - yesterday_close) / yesterday_close * 100.0
    result["gap_pct"] = round(gap, 2)

    if gap >= CEILING_GAP_MIN:
        result["locked"] = True
        result["queue_type"] = "BUY"
    elif gap <= -CEILING_GAP_MIN:
        result["locked"] = True
        result["queue_type"] = "SELL"
    else:
        result["reason"] = f"gap {gap:.1f}% - not locked (min {CEILING_GAP_MIN}%)"
        return result

    if avg_daily_volume and avg_daily_volume > 0 and today_volume and today_volume > 0:
        mins = _minutes_since_open()
        expected = max(0.02, mins / TOTAL_MARKET_MINUTES)
        today_frac = today_volume / avg_daily_volume
        heaviness = today_frac / expected
        result["heaviness"] = round(heaviness, 2)
        result["heavy"] = heaviness >= HEAVY_RATIO_MIN

    kind = "heavy" if result["heavy"] else "light"
    sign = "+" if result["queue_type"] == "BUY" else ""
    name = "BUY" if result["queue_type"] == "BUY" else "SELL"
    result["reason"] = f"queue {name} {kind} (gap {sign}{gap:.1f}%, heaviness {result['heaviness']}x)"

    return result


def should_trigger_call_surge(queue_info, minutes_into_session=None):
    if not queue_info or queue_info.get("queue_type") != "BUY":
        return False
    if not queue_info.get("locked"):
        return False
    mins = minutes_into_session if minutes_into_session is not None else _minutes_since_open()
    return mins <= 180