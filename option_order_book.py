# -*- coding: utf-8 -*-
"""
AHRAM OPTION ORDER BOOK  (نسخه‌ی سریع)
صف خرید/فروش قرارداد. اولویت: آخرین قیمت از دیتابیس (سریع).
"""
import sqlite3

try:
    import config as _config
except Exception:
    _config = None

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

try:
    import algotik_tse as att
    _HAS_ALGOTIK = True
except Exception:
    _HAS_ALGOTIK = False

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
}


def _last_price_from_db(symbol, db_path=None):
    if _config is None:
        return None
    try:
        conn = sqlite3.connect(db_path or _config.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute(
            "SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1",
            (symbol,)
        )
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return float(row[0])
    except Exception:
        return None
    return None


def get_option_inscode(symbol):
    if not _HAS_ALGOTIK:
        return None
    try:
        snapshot = att.get_market_snapshot()
    except Exception:
        return None
    stocks = snapshot.get("stocks")
    if stocks is None:
        return None
    row = stocks[(stocks["Symbol"] == symbol) & (stocks["InstrumentType"].isin([311, 312]))]
    if row.empty:
        return None
    return str(row.iloc[0]["InsCode"])


def _live_bid_ask(ins_code):
    if not _HAS_REQUESTS or not ins_code:
        return None
    url = f"https://cdn.tsetmc.com/api/BestLimits/{ins_code}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=6)
    except Exception:
        return None
    if response.status_code != 200 or not response.text.strip():
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    rows = data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                rows = v
                break
    if not rows:
        return None
    best = rows[0]
    buy = best.get("pMeDem") or best.get("priceBuy")
    sell = best.get("pMeOf") or best.get("priceSell")
    if buy is None and sell is None:
        return None
    return {
        "bid": float(buy) if buy is not None else None,
        "ask": float(sell) if sell is not None else None,
    }


def get_option_bid_ask(symbol, db_path=None):
    """صف خرید/فروش قرارداد. روش سریع: آخرین قیمت از دیتابیس."""
    last = _last_price_from_db(symbol, db_path)
    if last and last > 0:
        return {"bid": last, "ask": last, "source": "last_price"}
    ins_code = get_option_inscode(symbol)
    live = _live_bid_ask(ins_code)
    if live and live.get("ask") and live.get("bid"):
        live["source"] = "live"
        return live
    return None


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(get_option_bid_ask("ضهرم6045"))