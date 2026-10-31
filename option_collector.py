# -*- coding: utf-8 -*-
"""
جمع‌آوری داده‌ی آپشن از MarketWatchInit (نسخه‌ی اصلاح‌شده).

نگاشت فیلدهای خام (تأییدشده با صفحه‌ی TSETMC، ۱۴۰۵/۰۹/۱۰ = ۱۰:۳۱ یکشنبه):
  [2]  نماد
  [3]  نام قرارداد
  [4]  زمان آخرین به‌روزرسانی قیمت (HHMMSS)  <- برای تشخیص قیمت قدیمی
  [5]  اولین قیمت
  [6]  قیمت پایانی
  [7]  آخرین معامله           <- قیمت مبنا (مثل قبل)
  [8]  تعداد معاملات
  [9]  حجم معاملات           <- قبلاً اشتباهی به‌جای [8] به‌عنوان حجم خوانده می‌شد
  [10] ارزش معاملات
  [11] کمترین قیمت روز
  [12] بیشترین قیمت روز
  [13] قیمت دیروز
  [22] نوع: 311 = خرید (CALL)، 312 = فروش (PUT)
  [24] موقعیت‌های باز (open interest)

قیمت «تازه» یعنی زمان [4] کمتر از MAX_PRICE_AGE_MIN دقیقه از الان فاصله داشته باشد.
قیمت غیرتازه ذخیره می‌شود ولی با price_fresh=0 علامت می‌خورد؛ پایش خروج فقط روی price_fresh=1 کار می‌کند.
"""
import sys
import sqlite3
from datetime import datetime

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.tsetmc.com/",
}

MAX_PRICE_AGE_MIN = 30          # بیشتر از این = قیمت قدیمی
UNDERLYING_INFO = {"price": None, "yesterday": None, "volume": None}

NEW_COLUMNS = {"price_time": "TEXT", "price_age_min": "REAL", "price_fresh": "INTEGER",
               "bid_placeholder": "REAL", "trades_count": "REAL", "low_price": "REAL", "high_price": "REAL"}


def _get_underlying_price():
    try:
        url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{config.INS_CODE}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        info = r.json().get("closingPriceInfo", {})
        if info:
            return float(info.get("pDrCotVal", 0)), float(info.get("pClosing", 0)), float(info.get("qTotTran5J", 0))
    except Exception:
        pass
    return None, None, None


def _extract_from_name(name):
    strike, expire_date = 0, ""
    try:
        parts = name.split("-")
        if len(parts) >= 2:
            strike = float(parts[1])
        if len(parts) >= 3:
            expire_date = parts[2].strip()
    except Exception:
        pass
    return strike, expire_date


def _parse_jalali_date(date_str):
    try:
        import jdatetime
        parts = date_str.strip().split("/")
        if len(parts) != 3:
            return None
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        days = (jdatetime.date(y, m, d) - jdatetime.date.today()).days
        return days if days >= 0 else None
    except Exception:
        return None


def parse_hhmmss(value, now):
    """HHMMSS (مثل 122957) را به datetime امروز تبدیل می‌کند. None اگر نامعتبر."""
    s = str(value).strip().split(".")[0]
    if not s.isdigit():
        return None
    s = s.zfill(6)
    try:
        return now.replace(hour=int(s[0:2]), minute=int(s[2:4]), second=int(s[4:6]), microsecond=0)
    except ValueError:
        return None


def price_age_minutes(price_hhmmss, now):
    t = parse_hhmmss(price_hhmmss, now)
    if t is None:
        return None
    return (now - t).total_seconds() / 60


def ensure_columns(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(options)")
    existing = {row[1] for row in cur.fetchall()}
    for col, typ in NEW_COLUMNS.items():
        if col not in existing:
            try:
                cur.execute(f"ALTER TABLE options ADD COLUMN {col} {typ}")
            except Exception as e:
                print(f"[OPTION COLLECTOR] ستون {col} اضافه نشد: {e}")
    conn.commit()


def collect_options(now=None):
    global UNDERLYING_INFO
    now = now or datetime.now()

    price, yesterday, volume = _get_underlying_price()
    UNDERLYING_INFO.update({"price": price, "yesterday": yesterday, "volume": volume})

    try:
        r = requests.get(config.MARKET_WATCH_URL, headers=HEADERS, timeout=25)
        parts = r.text.strip().split("@")
        if len(parts) < 3:
            print("[OPTION COLLECTOR] فرمت غیرمنتظره")
            return
    except Exception as e:
        print(f"[OPTION COLLECTOR] خطا دریافت: {e}")
        return

    option_root = getattr(config, "OPTION_ROOT", None)
    rows = []
    stale_count = 0
    for item in parts[2].strip().split(";"):
        f = item.split(",")
        if len(f) < 25:
            continue
        if f[22].strip() not in ("311", "312"):
            continue
        symbol = f[2].strip()
        if option_root:
            if option_root not in symbol:
                continue
        elif config.UNDERLYING not in symbol:
            continue
        try:
            name = f[3].strip()
            last_trade = float(f[7]) if f[7] else 0.0
            final_price = float(f[6]) if f[6] else 0.0
            # قیمت مبنا: آخرین معامله؛ اگر صفر بود، قیمت پایانی
            option_price = last_trade if last_trade > 0 else final_price
            if option_price <= 0:
                continue

            age = price_age_minutes(f[4], now)
            fresh = 1 if (age is not None and 0 <= age <= MAX_PRICE_AGE_MIN) else 0

            strike_price, expire_date = _extract_from_name(name)
            if strike_price <= 0:
                continue
            days_to_expire = _parse_jalali_date(expire_date)
            if days_to_expire is None or days_to_expire < config.OPTION_MIN_DAYS:
                continue

            rows.append({
                "symbol": symbol,
                "option_type": "CALL" if f[22].strip() == "311" else "PUT",
                "stock_price": UNDERLYING_INFO.get("price") or 0,
                "option_price": option_price,
                "strike_price": strike_price,
                "expire_date": expire_date,
                "days_to_expire": days_to_expire,
                "volume": float(f[9]) if f[9] else 0.0,          # حجم معاملات
                "trades_count": float(f[8]) if f[8] else 0.0,    # تعداد معاملات
                "value": float(f[10]) if f[10] else 0.0,
                "open_interest": float(f[24]) if f[24] else 0.0,
                "low_price": float(f[11]) if f[11] else None,
                "high_price": float(f[12]) if f[12] else None,
                "price_time": str(f[4]).strip(),
                "price_age_min": round(age, 1) if age is not None else None,
                "price_fresh": fresh,
            })
            if not fresh:
                stale_count += 1
        except Exception:
            continue

    if not rows:
        print("[OPTION COLLECTOR] هیچ آپشنی پیدا نشد")
        return

    try:
        conn = sqlite3.connect(config.DATABASE_NAME)
        ensure_columns(conn)
        cur = conn.cursor()
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        for o in rows:
            cur.execute("""
                INSERT INTO options (
                    time, symbol, option_type, stock_price, option_price,
                    strike_price, expire_date, days_to_expire,
                    volume, value_traded, open_interest,
                    trades_count, low_price, high_price, price_time, price_age_min, price_fresh
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stamp, o["symbol"], o["option_type"], o["stock_price"], o["option_price"],
                o["strike_price"], o["expire_date"], o["days_to_expire"],
                o["volume"], o["value"], o["open_interest"],
                o["trades_count"], o["low_price"], o["high_price"],
                o["price_time"], o["price_age_min"], o["price_fresh"],
            ))
        conn.commit()
        conn.close()
        print("=" * 60)
        print(f"OPTION DATA FETCHED FROM TSETMC | {config.UNDERLYING} PRICE: {UNDERLYING_INFO.get('price')}")
        print(f"TOTAL OPTIONS: {len(rows)} | قیمت قدیمی (غیرتازه): {stale_count}")
        print("=" * 60)
    except Exception as e:
        print(f"[OPTION COLLECTOR] خطا ذخیره: {e}")


if __name__ == "__main__":
    collect_options()