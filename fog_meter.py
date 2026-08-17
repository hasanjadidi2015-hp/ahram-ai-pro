# -*- coding: utf-8 -*-
import sqlite3
from option_engine import OptionEngine, compute_historical_volatility


def measure(stock_price, db):
    """Fog meter: IV of ATM option vs historical realized vol.
    Returns (level, ratio, advice). level: CLEAN/LIGHT/FOG/DENSE."""
    try:
        stock_price = float(stock_price)
    except (TypeError, ValueError):
        return ("UNKNOWN", None, "no stock price")
    if stock_price <= 0:
        return ("UNKNOWN", None, "no stock price")
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT MAX(time) FROM options")
        r = cur.fetchone()
        latest = r[0] if r else None
        if not latest:
            conn.close()
            return ("UNKNOWN", None, "no option data")
        cur.execute(
            "SELECT symbol, strike_price, option_price, days_to_expire "
            "FROM options WHERE option_type='CALL' AND time=? "
            "AND option_price>0 AND days_to_expire>=7",
            (latest,),
        )
        opts = cur.fetchall()
        conn.close()
    except Exception:
        return ("UNKNOWN", None, "db error")
    if not opts:
        return ("UNKNOWN", None, "no CALL options")
    try:
        atm = min(opts, key=lambda o: abs(float(o[1]) - stock_price))
    except Exception:
        return ("UNKNOWN", None, "no ATM option")
    hv = compute_historical_volatility()
    if not hv or hv <= 0:
        return ("UNKNOWN", None, "no historical volatility")
    try:
        eng = OptionEngine()
        a = eng.analyze(stock_price, float(atm[1]), float(atm[2]), int(atm[3] or 0), "CALL")
    except Exception:
        return ("UNKNOWN", None, "engine error")
    ratio = a.get("iv_premium_ratio")
    if not ratio:
        return ("UNKNOWN", None, "IV not computable")
    if ratio < 1.3:
        return ("CLEAN", ratio, "fog thin - good for buying")
    elif ratio < 1.8:
        return ("LIGHT", ratio, "light fog - OK")
    elif ratio < 2.5:
        return ("FOG", ratio, "fog thick - caution, spread better")
    else:
        return ("DENSE", ratio, "fog dense - IV crush risk, avoid naked")