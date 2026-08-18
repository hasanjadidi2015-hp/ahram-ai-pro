# -*- coding: utf-8 -*-
"""
جمع‌آوری داده‌ی آپشن از MarketWatchInit
نسخه نهایی: قیمت نماد پایه از API جداگانه
"""
import sys
import sqlite3
import requests
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.tsetmc.com/",
}

UNDERLYING_INFO = {"price": None, "yesterday": None, "volume": None}


def _get_underlying_price():
    """دریافت قیمت نماد پایه از API جداگانه"""
    try:
        url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{config.INS_CODE}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        info = data.get("closingPriceInfo", {})
        if info:
            price = float(info.get("pDrCotVal", 0))
            yesterday = float(info.get("pClosing", 0))
            volume = float(info.get("qTotTran5J", 0))
            return price, yesterday, volume
    except:
        pass
    return None, None, None


def _extract_from_name(name):
    """استخراج strike و تاریخ از نام قرارداد"""
    strike = 0
    expire_date = ""
    try:
        parts = name.split("-")
        if len(parts) >= 2:
            strike = float(parts[1])
        if len(parts) >= 3:
            expire_date = parts[2].strip()
    except:
        pass
    return strike, expire_date


def _parse_jalali_date(date_str):
    """تبدیل تاریخ شمسی به تعداد روز تا سررسید"""
    try:
        import jdatetime
        parts = date_str.strip().split("/")
        if len(parts) != 3:
            return None
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        expire_jalali = jdatetime.date(year, month, day)
        today_jalali = jdatetime.date.today()
        days = (expire_jalali - today_jalali).days
        return days if days >= 0 else None
    except:
        return None


def collect_options():
    global UNDERLYING_INFO

    # دریافت قیمت نماد پایه از API جداگانه
    price, yesterday, volume = _get_underlying_price()
    UNDERLYING_INFO["price"] = price
    UNDERLYING_INFO["yesterday"] = yesterday
    UNDERLYING_INFO["volume"] = volume

    # دریافت آپشن‌ها از MarketWatchInit
    try:
        r = requests.get(config.MARKET_WATCH_URL, headers=HEADERS, timeout=25)
        text = r.text.strip()
        parts = text.split("@")
        if len(parts) < 3:
            print("[OPTION COLLECTOR] فرمت غیرمنتظره")
            return
    except Exception as e:
        print(f"[OPTION COLLECTOR] خطا دریافت: {e}")
        return

    instruments = parts[2].strip().split(";")

    # جمع‌آوری آپشن‌ها
    option_root = getattr(config, "OPTION_ROOT", None)
    options_list = []

    for item in instruments:
        f = item.split(",")
        if len(f) < 25:
            continue

        ins_type = f[22].strip()
        if ins_type not in ("311", "312"):
            continue

        symbol = f[2].strip()

        # فیلتر بر اساس نماد پایه
        if option_root:
            if option_root not in symbol:
                continue
        else:
            if config.UNDERLYING not in symbol:
                continue

        try:
            name = f[3].strip()

            # قیمت آپشن: اول f[5] (آخرین معامله)، اگر نبود f[6] (پایانی)
            option_price = float(f[5]) if f[5] else 0
            if option_price <= 0:
                option_price = float(f[6]) if f[6] else 0
            if option_price <= 0:
                continue

            # حجم و ارزش
            volume = float(f[8]) if f[8] else 0
            value = float(f[10]) if f[10] else 0
            open_interest = float(f[24]) if f[24] else 0

            # استخراج strike و تاریخ از نام قرارداد
            strike_price, expire_date = _extract_from_name(name)
            if strike_price <= 0:
                continue

            # محاسبه روز تا سررسید
            days_to_expire = _parse_jalali_date(expire_date)
            if days_to_expire is None or days_to_expire < config.OPTION_MIN_DAYS:
                continue

            option_type = "CALL" if ins_type == "311" else "PUT"

            options_list.append({
                "symbol": symbol,
                "name": name,
                "option_type": option_type,
                "stock_price": UNDERLYING_INFO.get("price") or 0,
                "option_price": option_price,
                "strike_price": strike_price,
                "expire_date": expire_date,
                "days_to_expire": days_to_expire,
                "volume": volume,
                "value": value,
                "open_interest": open_interest,
            })

        except Exception:
            continue

    if not options_list:
        print("[OPTION COLLECTOR] هیچ آپشنی پیدا نشد")
        return

    # ذخیره در دیتابیس
    try:
        conn = sqlite3.connect(config.DATABASE_NAME)
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for opt in options_list:
            cur.execute("""
                INSERT INTO options (
                    time, symbol, option_type, stock_price, option_price,
                    strike_price, expire_date, days_to_expire,
                    volume, value_traded, open_interest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now, opt["symbol"], opt["option_type"], opt["stock_price"],
                opt["option_price"], opt["strike_price"], opt["expire_date"],
                opt["days_to_expire"], opt["volume"], opt["value"], opt["open_interest"],
            ))

        conn.commit()
        conn.close()

        print("=" * 60)
        print(f"OPTION DATA FETCHED FROM TSETMC")
        print(f"{config.UNDERLYING} PRICE : {UNDERLYING_INFO.get('price')}")
        print(f"TOTAL OPTIONS : {len(options_list)}")
        print("=" * 60)

        # نمایش بهترین کاندیدها
        sorted_opts = sorted(options_list, key=lambda x: x["volume"], reverse=True)
        print("TOP CANDIDATES (ATM + liquid):")
        stock_p = UNDERLYING_INFO.get("price") or 0
        for opt in sorted_opts[:5]:
            ratio = opt["strike_price"] / stock_p if stock_p > 0 else 0
            print(f"  {opt['option_type']} {opt['symbol']:<15} "
                  f"STRIKE={int(opt['strike_price'])}  "
                  f"PRICE={int(opt['option_price'])}  "
                  f"VOL={int(opt['volume'])}  "
                  f"DAYS={opt['days_to_expire']}  "
                  f"ratio={ratio:.2f}")

    except Exception as e:
        print(f"[OPTION COLLECTOR] خطا ذخیره: {e}")


if __name__ == "__main__":
    collect_options()