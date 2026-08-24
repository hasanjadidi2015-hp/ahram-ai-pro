# -*- coding: utf-8 -*-
"""
تابلوخوانی زنده دارایی پایه از TSETMC.

- دریافت پنج ردیف اول سفارش خرید/فروش
- ذخیره در SQLite
- محاسبه اسپرد و عدم‌تعادل حجم
- اگر داده ناقص باشد، فشار UNKNOWN برمی‌گرداند؛
  نه BUY_HEAVY یا SELL_HEAVY جعلی.
"""

import sqlite3
import time
from datetime import datetime

import requests

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


def _to_float(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _to_int(value, default=0):
    try:
        return int(float(value)) if value is not None else default
    except (TypeError, ValueError):
        return default


def _get_field(data, *names, default=0):
    """اولین فیلد موجود و معتبر را برمی‌گرداند."""
    if not isinstance(data, dict):
        return default

    for name in names:
        if name in data and data[name] is not None:
            return data[name]

    return default


def fetch_order_book(ins_code=None, max_retries=2):
    """دریافت عمق سفارش نماد از TSETMC."""
    ins_code = ins_code or config.INS_CODE

    url = f"https://cdn.tsetmc.com/api/BestLimits/{ins_code}"

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=(4, 10),
            )
        except requests.exceptions.RequestException as e:
            print(f"[ORDER-BOOK] CONNECTION ERROR ({attempt}/{max_retries}): {e}")
            time.sleep(1)
            continue

        if response.status_code != 200:
            print(
                f"[ORDER-BOOK] SERVER ERROR ({attempt}/{max_retries}): "
                f"HTTP {response.status_code}"
            )
            time.sleep(1)
            continue

        if not response.text or not response.text.strip():
            print(f"[ORDER-BOOK] EMPTY RESPONSE ({attempt}/{max_retries})")
            time.sleep(1)
            continue

        try:
            data = response.json()
        except ValueError:
            print("[ORDER-BOOK] INVALID JSON:", response.text[:300])
            return None

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            levels = (
                data.get("bestLimits")
                or data.get("bestLimitsInfo")
                or data.get("data")
                or []
            )

            if isinstance(levels, list):
                return levels

        print("[ORDER-BOOK] UNKNOWN RESPONSE SHAPE:", str(data)[:500])
        return None

    return None


def _ensure_table(cur):
    """ساخت جدول Order Book در صورت نبودن."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            level INTEGER,
            buy_count INTEGER,
            buy_volume REAL,
            buy_price REAL,
            sell_price REAL,
            sell_volume REAL,
            sell_count INTEGER
        )
    """)


def _parse_levels(levels):
    """
    پشتیبانی از نام‌های متداول فیلدهای API TSETMC.

    خرید:
      pMeDem / qTitMeDem / zOrdMeDem

    فروش:
      pMeOf / qTitMeOf / zOrdMeOf

    بعضی نسخه‌های قدیمی:
      pMeArz / qTitMeArz / zOrdMeArz
    """
    rows = []

    for index, item in enumerate(levels, start=1):
        if not isinstance(item, dict):
            continue

        level = _to_int(
            _get_field(
                item,
                "number",
                "numberOfRow",
                "row",
                "rEven",
                default=index,
            ),
            default=index,
        )

        buy_count = _to_int(
            _get_field(
                item,
                "zOrdMeDem",
                "buyOrderCount",
                "buy_count",
            )
        )

        buy_volume = _to_float(
            _get_field(
                item,
                "qTitMeDem",
                "buyVolume",
                "buy_volume",
            )
        )

        buy_price = _to_float(
            _get_field(
                item,
                "pMeDem",
                "buyPrice",
                "buy_price",
            )
        )

        sell_price = _to_float(
            _get_field(
                item,
                "pMeOf",
                "pMeArz",
                "sellPrice",
                "sell_price",
            )
        )

        sell_volume = _to_float(
            _get_field(
                item,
                "qTitMeOf",
                "qTitMeArz",
                "sellVolume",
                "sell_volume",
            )
        )

        sell_count = _to_int(
            _get_field(
                item,
                "zOrdMeOf",
                "zOrdMeArz",
                "sellOrderCount",
                "sell_count",
            )
        )

        # اگر هیچ سمت معتبری وجود نداشت، این ردیف بی‌فایده است
        if buy_price <= 0 and sell_price <= 0:
            continue

        rows.append((
            level,
            buy_count,
            buy_volume,
            buy_price,
            sell_price,
            sell_volume,
            sell_count,
        ))

    return sorted(rows, key=lambda row: row[0])


def _save_rows(db_path, rows, now):
    """ذخیره داده خام سفارش‌ها در دیتابیس."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        _ensure_table(cur)

        for (
            level,
            buy_count,
            buy_volume,
            buy_price,
            sell_price,
            sell_volume,
            sell_count,
        ) in rows:
            cur.execute("""
                INSERT INTO order_book (
                    time,
                    level,
                    buy_count,
                    buy_volume,
                    buy_price,
                    sell_price,
                    sell_volume,
                    sell_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now,
                level,
                buy_count,
                buy_volume,
                buy_price,
                sell_price,
                sell_volume,
                sell_count,
            ))

        conn.commit()
        conn.close()

    except Exception as e:
        print("[ORDER-BOOK] DB ERROR:", e)


def collect_order_book(db_path=None, ins_code=None):
    """
    دریافت، ذخیره و تحلیل خلاصه Order Book.

    اگر قیمت/حجم فروش یا خرید ناقص باشد:
      pressure = UNKNOWN
      imbalance_pct = None
      spread_pct = None
    """
    db_path = db_path or config.DATABASE_NAME
    ins_code = ins_code or config.INS_CODE

    levels = fetch_order_book(ins_code=ins_code)

    if not levels:
        return None

    rows = _parse_levels(levels)

    if not rows:
        print(
            "[ORDER-BOOK] هیچ ردیف معتبر قابل‌پردازش نبود. "
            "نمونه پاسخ:",
            str(levels[:1])[:700],
        )
        return None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_rows(db_path, rows, now)

    total_buy_volume = sum(row[2] for row in rows if row[3] > 0)
    total_sell_volume = sum(row[5] for row in rows if row[4] > 0)

    total_buy_count = sum(row[1] for row in rows if row[3] > 0)
    total_sell_count = sum(row[6] for row in rows if row[4] > 0)

    # اولین ردیف معتبر با قیمت خرید / فروش
    best_buy = next(
        (row[3] for row in rows if row[3] > 0),
        None,
    )

    best_sell = next(
        (row[4] for row in rows if row[4] > 0),
        None,
    )

    # بدون هر دو سمت، تحلیل فشار معتبر نیست
    market_is_valid = (
        best_buy is not None
        and best_sell is not None
        and best_buy > 0
        and best_sell > 0
        and total_buy_volume > 0
        and total_sell_volume > 0
        and best_sell >= best_buy
    )

    if not market_is_valid:
        return {
            "time": now,
            "best_buy": best_buy,
            "best_sell": best_sell,
            "spread": None,
            "spread_pct": None,
            "total_buy_volume": total_buy_volume,
            "total_sell_volume": total_sell_volume,
            "total_buy_count": total_buy_count,
            "total_sell_count": total_sell_count,
            "imbalance_pct": None,
            "pressure": "UNKNOWN",
            "is_valid": False,
            "reason": "اطلاعات خرید یا فروش ناقص/نامعتبر است",
            "levels": rows,
        }

    spread = best_sell - best_buy
    spread_pct = round((spread / best_buy) * 100, 3)

    imbalance_pct = round(
        (
            (total_buy_volume - total_sell_volume)
            / (total_buy_volume + total_sell_volume)
        ) * 100,
        1,
    )

    if imbalance_pct > 20:
        pressure = "BUY_HEAVY"
    elif imbalance_pct < -20:
        pressure = "SELL_HEAVY"
    else:
        pressure = "BALANCED"

    return {
        "time": now,
        "best_buy": best_buy,
        "best_sell": best_sell,
        "spread": spread,
        "spread_pct": spread_pct,
        "total_buy_volume": total_buy_volume,
        "total_sell_volume": total_sell_volume,
        "total_buy_count": total_buy_count,
        "total_sell_count": total_sell_count,
        "imbalance_pct": imbalance_pct,
        "pressure": pressure,
        "is_valid": True,
        "reason": None,
        "levels": rows,
    }


if __name__ == "__main__":
    result = collect_order_book()

    print("=" * 55)
    print("ORDER BOOK TEST")
    print("=" * 55)

    if not result:
        print("❌ هیچ داده‌ای از تابلو دریافت نشد.")

    elif not result["is_valid"]:
        print("⚠️ داده تابلو ناقص است؛ برای سیگنال قابل‌استفاده نیست.")
        print("دلیل:", result["reason"])
        print("بهترین خرید:", result["best_buy"])
        print("بهترین فروش:", result["best_sell"])
        print("حجم خرید:", f"{result['total_buy_volume']:,.0f}")
        print("حجم فروش:", f"{result['total_sell_volume']:,.0f}")

    else:
        print("✅ داده تابلو معتبر است")
        print("بهترین خرید:", result["best_buy"])
        print("بهترین فروش:", result["best_sell"])
        print("اسپرد:", result["spread"], f"({result['spread_pct']}%)")
        print("حجم خرید:", f"{result['total_buy_volume']:,.0f}")
        print("حجم فروش:", f"{result['total_sell_volume']:,.0f}")
        print("عدم‌تعادل:", f"{result['imbalance_pct']}%")
        print("فشار:", result["pressure"])