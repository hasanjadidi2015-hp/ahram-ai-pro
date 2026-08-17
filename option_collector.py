# -*- coding: utf-8 -*-
"""
جمع‌آوری داده‌ی آپشن از MarketWatchInit
نسخه اصلاح‌شده: فیلتر بر اساس OPTION_ROOT
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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
}

# اطلاعات نماد پایه
UNDERLYING_INFO = {
    "price": None,
    "yesterday": None,
    "volume": None,
}


def _parse_jalali_date(date_str):
    """تبدیل تاریخ شمسی (مثل 1405/06/13) به تعداد روز تا سررسید"""
    try:
        import jdatetime
        parts = date_str.strip().split("/")
        if len(parts) != 3:
            return None, None
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        expire_jalali = jdatetime.date(year, month, day)
        today_jalali = jdatetime.date.today()
        delta = expire_jalali - today_jalali
        days = delta.days
        if days < 0:
            return None, None
        expire_greg = expire_jalali.togregorian().strftime("%Y-%m-%d")
        return days, expire_greg
    except Exception:
        return None, None


def collect_options():
    """جمع‌آوری قراردادهای آپشن از MarketWatchInit"""
    global UNDERLYING_INFO

    try:
        r = requests.get(config.MARKET_WATCH_URL, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as e:
        print(f"[OPTION COLLECTOR] خطا دریافت: {e}")
        return

    text = r.text.strip()
    parts = text.split("@")
    if len(parts) < 3:
        print("[OPTION COLLECTOR] فرمت غیرمنتظره")
        return

    instruments = parts[2].strip().split(";")

    # پیدا کردن نماد پایه
    underlying_name = config.UNDERLYING
    for item in instruments:
        f = item.split(",")
        if len(f) < 23:
            continue
        if f[2].strip() == underlying_name:
            try:
                price = float(f[1]) if f[1] else None
                vol = float(f[5]) if f[5] else None
                yesterday = float(f[7]) if f[7] else None
                UNDERLYING_INFO["price"] = price
                UNDERLYING_INFO["volume"] = vol
                UNDERLYING_INFO["yesterday"] = yesterday
            except (ValueError, IndexError):
                pass
            break

    # جمع‌آوری آپشن‌ها
    option_root = getattr(config, "OPTION_ROOT", None)
    options_list = []

    for item in instruments:
        f = item.split(",")
        if len(f) < 23:
            continue

        # نوع ابزار: 311=اختیار خرید، 312=اختیار فروش
        ins_type = f[22].strip()
        if ins_type not in ("311", "312"):
            continue

        name = f[2].strip()

        # فیلتر بر اساس ریشه آپشن
        if option_root:
            if option_root not in name:
                continue
        else:
            if config.UNDERLYING not in name:
                continue

        try:
            symbol = f[0].strip() if len(f) > 0 else name
            stock_price = float(f[1]) if f[1] else 0
            last_trade = float(f[6]) if f[6] else 0
            close_price = float(f[7]) if f[7] else 0
            volume = float(f[9]) if f[9] else 0
            value = float(f[10]) if f[10] else 0
            open_interest = float(f[12]) if f[12] else 0

            # قیمت آپشن
            option_price = last_trade if last_trade > 0 else close_price
            if option_price <= 0:
                continue

            # قیمت اعمال
            strike_price = 0
            for i in range(13, min(20, len(f))):
                try:
                    val = float(f[i])
                    if val > 0 and val != option_price and val != stock_price:
                        strike_price = val
                        break
                except ValueError:
                    continue

            if strike_price <= 0:
                continue

            # تاریخ سررسید
            expire_date = f[21].strip() if len(f) > 21 else ""
            days_to_expire, expire_greg = _parse_jalali_date(expire_date)

            if days_to_expire is None or days_to_expire < config.OPTION_MIN_DAYS:
                continue

            option_type = "CALL" if ins_type == "311" else "PUT"

            options_list.append({
                "symbol": name,
                "option_type": option_type,
                "stock_price": stock_price,
                "option_price": option_price,
                "strike_price": strike_price,
                "expire_date": expire_date,
                "expire_greg": expire_greg,
                "days_to_expire": days_to_expire,
                "volume": volume,
                "value": value,
                "open_interest": open_interest,
            })

        except (ValueError, IndexError):
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
                now,
                opt["symbol"],
                opt["option_type"],
                opt["stock_price"],
                opt["option_price"],
                opt["strike_price"],
                opt["expire_date"],
                opt["days_to_expire"],
                opt["volume"],
                opt["value"],
                opt["open_interest"],
            ))

        conn.commit()
        conn.close()

        print("=" * 60)
        print(f"OPTION DATA FETCHED FROM TSETMC (MarketWatchInit)")
        print(f"{config.UNDERLYING} PRICE : {UNDERLYING_INFO.get('price')}")
        print(f"TOTAL OPTIONS : {len(options_list)}")
        print("=" * 60)

        # نمایش بهترین کاندیدها
        sorted_opts = sorted(options_list, key=lambda x: x["volume"], reverse=True)
        print("TOP CANDIDATES (ATM + liquid):")
        stock_price = UNDERLYING_INFO.get("price") or 0
        for opt in sorted_opts[:5]:
            ratio = opt["strike_price"] / stock_price if stock_price > 0 else 0
            print(f"  {opt['option_type']} {opt['symbol']:<20} "
                  f"STRIKE={int(opt['strike_price'])}    "
                  f"PRICE={opt['option_price']}     "
                  f"VOL={int(opt['volume'])}    "
                  f"DAYS={opt['days_to_expire']}   "
                  f"ratio={ratio:.2f}")

    except Exception as e:
        print(f"[OPTION COLLECTOR] خطا ذخیره: {e}")


if __name__ == "__main__":
    collect_options()