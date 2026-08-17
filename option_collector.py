# -*- coding: utf-8 -*-
"""
AHRAM OPTION COLLECTOR
دریافت دیتای زنده‌ی اپشن‌ها از MarketWatchInit + ذخیره.
"""
import sys
import time
import sqlite3
from datetime import datetime

import requests

try:
    import jdatetime
    _HAS_JDATETIME = True
except ImportError:
    _HAS_JDATETIME = False

import config

_MW_CACHE = {"text": None, "ts": 0}
_MW_TTL = 90

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class OptionCollector:
    def __init__(self):
        self.conn = sqlite3.connect(config.DATABASE_NAME)
        self.cursor = self.conn.cursor()

    def save_option(self, symbol, option_type, stock_price, option_price,
                    strike_price, expire_date, days_to_expire, volume,
                    value_traded=0, open_interest=0):
        self.cursor.execute(
            """
            INSERT INTO options
            (time, symbol, option_type, stock_price, option_price,
             strike_price, expire_date, days_to_expire, volume,
             value_traded, open_interest)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), symbol, option_type,
             stock_price, option_price, strike_price, expire_date,
             days_to_expire, volume, value_traded, open_interest)
        )
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()


def _to_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _parse_strike_expire(name):
    parts = name.split("-")
    if len(parts) < 3:
        return None, None
    strike_str = parts[1].strip()
    expire_str = parts[2].strip()
    try:
        strike = int(float(strike_str.replace(",", "")))
    except ValueError:
        return None, None
    digits = expire_str.split("/")
    if len(digits) == 3:
        y, m, d = digits
        try:
            y = int(y)
            if y < 100:
                y = 1400 + y
            expire_jalali = f"{y:04d}/{int(m):02d}/{int(d):02d}"
        except ValueError:
            return strike, expire_str
    else:
        return strike, expire_str
    return strike, expire_jalali


def _days_to_expire(expire_jalali):
    if not _HAS_JDATETIME:
        return 30
    try:
        y, m, d = expire_jalali.split("/")
        exp_g = jdatetime.date(int(y), int(m), int(d)).togregorian()
        today_g = jdatetime.date.today().togregorian()
        return max(0, (exp_g - today_g).days)
    except Exception:
        return 30


def _select_best_option(options, stock_price):
    candidates = []
    for o in options:
        if config.OPTION_TYPE != "ALL" and o["option_type"] != config.OPTION_TYPE:
            continue
        if o["volume"] < config.OPTION_MIN_VOLUME:
            continue
        if o["days_to_expire"] < config.OPTION_MIN_DAYS:
            continue
        ratio = o["strike_price"] / stock_price if stock_price else 0
        if ratio < config.STRIKE_RATIO_MIN or ratio > config.STRIKE_RATIO_MAX:
            continue
        candidates.append(o)
    candidates.sort(key=lambda x: x["volume"], reverse=True)
    print("-" * 60)
    print("TOP CANDIDATES (ATM + liquid):")
    for o in candidates[:3]:
        ratio = o["strike_price"] / stock_price
        print(f"  {o['option_type']} {o['symbol']:<16} STRIKE={o['strike_price']:<7} "
              f"PRICE={o['option_price']:<9} VOL={int(o['volume']):<10} "
              f"DAYS={o['days_to_expire']:<4} ratio={ratio:.2f}")
    print("-" * 60)
    if not candidates:
        return None
    best = candidates[0]
    print("SELECTED:", best["symbol"], "| STRIKE", best["strike_price"],
          "| PRICE", best["option_price"], "| DAYS", best["days_to_expire"])
    return best


UNDERLYING_INFO = {}


def collect_options():
    global UNDERLYING_INFO
    now = time.time()
    if _MW_CACHE["text"] and (now - _MW_CACHE["ts"]) < _MW_TTL:
        text = _MW_CACHE["text"]
    else:
        try:
            r = requests.get(config.MARKET_WATCH_URL, timeout=25)
        except Exception as e:
            print("CONNECTION ERROR:", e)
            return False
        if r.status_code != 200:
            print("SERVER ERROR:", r.status_code)
            return False
        text = r.text.strip()
        _MW_CACHE["text"] = text
        _MW_CACHE["ts"] = now
    parts = text.split("@")
    if len(parts) < 3:
        print("UNEXPECTED FORMAT")
        return False
    instruments = parts[2].strip().split(";")

    ahrm_price = None
    ahrm_close = None
    ahrm_vol = None
    for item in instruments:
        f = item.split(",")
        if len(f) < 23:
            continue
        if f[2].strip() == config.UNDERLYING:
            last = _to_float(f[7])
            close = _to_float(f[6])
            vol = _to_float(f[9])
            ahrm_price = last if last > 0 else close
            ahrm_close = close
            ahrm_vol = vol

    if ahrm_price is None:
        print(config.UNDERLYING, "PRICE NOT FOUND")
        UNDERLYING_INFO = {}
        return False

    UNDERLYING_INFO = {"price": ahrm_price, "yesterday": ahrm_close, "volume": ahrm_vol}

    options = []
    for item in instruments:
        f = item.split(",")
        if len(f) < 23:
            continue
        name = f[3].strip()
        ins_type = f[22].strip()
        if ins_type not in ("311", "312"):
            continue
        if config.UNDERLYING not in name:
            continue
        strike, expire = _parse_strike_expire(name)
        if strike is None:
            continue
        last = _to_float(f[7])
        close = _to_float(f[6])
        price = last if last > 0 else close
        if price <= 0:
            continue
        volume = _to_float(f[9])
        value = _to_float(f[10])
        otype = "CALL" if ins_type == "311" else "PUT"
        days = _days_to_expire(expire)
        options.append({
            "symbol": f[2].strip(), "option_type": otype, "stock_price": ahrm_price,
            "option_price": price, "strike_price": strike, "expire_date": expire,
            "days_to_expire": days, "volume": volume, "value_traded": value,
        })

    print("=" * 60)
    print("OPTION DATA FETCHED FROM TSETMC (MarketWatchInit)")
    print(config.UNDERLYING, "PRICE :", int(ahrm_price))
    print("TOTAL OPTIONS :", len(options))
    print("=" * 60)

    if not _HAS_JDATETIME:
        print("WARNING: jdatetime نصب نیست.  pip install jdatetime")

    _select_best_option(options, ahrm_price)

    conn = sqlite3.connect(config.DATABASE_NAME)
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved = 0
    for o in options:
        cur.execute(
            """
            INSERT INTO options
            (time, symbol, option_type, stock_price, option_price, strike_price,
             expire_date, days_to_expire, volume, value_traded, open_interest)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (now_str, o["symbol"], o["option_type"], o["stock_price"], o["option_price"],
             o["strike_price"], o["expire_date"], o["days_to_expire"],
             o["volume"], o["value_traded"], o["volume"])
        )
        saved += 1
    conn.commit()
    conn.close()
    print(f"OPTION CHAIN SAVED: {saved} contracts (MarketWatchInit - سریع)")
    return True


if __name__ == "__main__":
    collect_options()