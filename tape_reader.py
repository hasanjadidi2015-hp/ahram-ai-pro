# -*- coding: utf-8 -*-
import sqlite3

SYMBOL_CONFIG = {
    "اهرم": {
        "volume_mult": 3.0, "saraneh_min_rial": 3e8, "bs_ratio_min": 1.5,
        "inflow_min_rial": 5e9,
    },
    "شستا": {
        "volume_mult": 2.0, "saraneh_min_rial": 2.5e8, "bs_ratio_min": 1.3,
        "inflow_min_rial": 1, "trades_min": 5000, "price_change_min": 1.0,
    },
    "وبملت": {
        "volume_mult": 2.0, "saraneh_min_rial": 2.5e8, "bs_ratio_min": 1.2,
        "inflow_min_rial": 1, "inst_buy_max": 0.30, "price_change_min": 0.01,
    },
}
DEFAULT_CONFIG = {
    "volume_mult": 2.5, "saraneh_min_rial": 2.5e8, "bs_ratio_min": 1.3,
    "inflow_min_rial": 1,
}


def _cfg_for(symbol):
    return SYMBOL_CONFIG.get(symbol, DEFAULT_CONFIG)


def compute(cfg, buy_i, sell_i, buy_n, buy_count_i, sell_count_i,
            price, today_vol, avg_vol, today_trades, yesterday_close):
    conds = {}
    try:
        from datetime import datetime as _dt
        _nm = _dt.now().hour * 60 + _dt.now().minute
        _el = max(1, min(210, _nm - 540))
        _tf = _el / 210.0
    except Exception:
        _tf = 1.0
    _vr = (today_vol / avg_vol / _tf) if (avg_vol and avg_vol > 0 and _tf > 0) else 0.0
    conds["volume"] = _vr >= cfg["volume_mult"]
    saraneh = (buy_i * price / buy_count_i) if buy_count_i else 0.0
    conds["saraneh"] = saraneh >= cfg["saraneh_min_rial"]
    ratio = (buy_count_i / sell_count_i) if sell_count_i else 0.0
    conds["bs_ratio"] = ratio >= cfg["bs_ratio_min"]
    inflow = (buy_i - sell_i) * price
    conds["inflow"] = inflow >= cfg["inflow_min_rial"]
    bp = (buy_i / buy_count_i) if buy_count_i else 0.0
    sp = (sell_i / sell_count_i) if sell_count_i else 0.0
    conds["buyer_power"] = bp > sp
    if cfg.get("trades_min"):
        conds["trades"] = today_trades >= cfg["trades_min"]
    if cfg.get("inst_buy_max") is not None and cfg["inst_buy_max"] < 1.0:
        inst_pct = (buy_n / today_vol) if today_vol else 1.0
        conds["inst_buy"] = inst_pct <= cfg["inst_buy_max"]
    if cfg.get("price_change_min") is not None:
        change = ((price - yesterday_close) / yesterday_close * 100) if yesterday_close else 0.0
        conds["price_change"] = change >= cfg["price_change_min"]
    total = len(conds)
    score = sum(1 for v in conds.values() if v)
    passed = score >= total - 1
    details = {
        "score": score, "total": total, "passed": passed,
        "saraneh_toman": round(saraneh / 10, 0),
        "bs_ratio": round(ratio, 2),
        "inflow_b_toman": round(inflow / 1e10, 2),
        "vol_ratio": round(today_vol / avg_vol, 2) if avg_vol else 0,
        "conds": conds,
    }
    return passed, score, details


def _get_market_data(db):
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT last_price, volume, trades, substr(time,1,10) FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        if not r:
            conn.close()
            return 0, 0, 0, 0, 0
        price = float(r[0] or 0)
        today_vol = float(r[1] or 0)
        today_trades = float(r[2] or 0)
        today_date = r[3]
        cur.execute("SELECT closing_price FROM prices WHERE substr(time,1,10)!=? AND closing_price IS NOT NULL AND closing_price>0 ORDER BY id DESC LIMIT 1", (today_date,))
        yr = cur.fetchone()
        yesterday_close = float(yr[0]) if yr and yr[0] else 0.0
        cur.execute("SELECT substr(time,1,10) d, MAX(volume) v FROM prices WHERE volume>0 GROUP BY d ORDER BY d DESC LIMIT 31")
        rows = [float(x[1]) for x in cur.fetchall() if x[1] and float(x[1]) > 0]
        conn.close()
        if len(rows) >= 6:
            rows.sort()
            trimmed = rows[1:-1]
            avg_vol = sum(trimmed) / len(trimmed)
        elif rows:
            avg_vol = sum(rows) / len(rows)
        else:
            avg_vol = 0
        return price, today_vol, avg_vol, today_trades, yesterday_close
    except Exception:
        return 0, 0, 0, 0, 0


def evaluate(db=None, ins_code=None):
    if db is None:
        import config
        db = config.DATABASE_NAME
    try:
        import algotik_tse as att
        import config
        if ins_code is None:
            ins_code = config.INS_CODE
        ct = att.get_market_client_type()
    except Exception as e:
        return (None, 0, {"error": "algotik unavailable: %s" % e})
    try:
        row = ct[ct["InsCode"].astype(str) == str(ins_code)]
        if row.empty:
            return (None, 0, {"error": "symbol not in client type"})
        r = row.iloc[0]
        buy_i = float(r["Buy_I_Volume"])
        sell_i = float(r["Sell_I_Volume"])
        buy_n = float(r.get("Buy_N_Volume", 0) or 0)
        buy_count_i = float(r.get("Buy_I_Count", 0) or 0)
        sell_count_i = float(r.get("Sell_I_Count", 0) or 0)
    except Exception as e:
        return (None, 0, {"error": "client type parse: %s" % e})
    price, today_vol, avg_vol, today_trades, yesterday_close = _get_market_data(db)
    symbol = None
    try:
        import config
        symbol = config.UNDERLYING
    except Exception:
        pass
    cfg = _cfg_for(symbol)
    return compute(cfg, buy_i, sell_i, buy_n, buy_count_i, sell_count_i,
                   price, today_vol, avg_vol, today_trades, yesterday_close)