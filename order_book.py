# -*- coding: utf-8 -*-
"""
تابلوخوانی زنده -- عمق سفارش خرید/فروش (۵ ردیف اول) خود سهم، از TSETMC.

فیکس 2026-08-31: باگ اصلی پیدا شد!
API اصلی TSETMC BestLimits فیلدها را با نام pMeOf/qTitMeOf/zOrdMeOf برمی‌گرداند
ولی کد قبلی فقط دنبال pMeArz/qTitMeArz/zOrdMeArz می‌گشت → فروش همیشه 0 می‌شد
و صف خرید کاذب نشان می‌داد در حالی که بازار منفی بود.

این نسخه هر دو نام را چک می‌کند:
- خرید: pMeDem / qTitMeDem / zOrdMeDem
- فروش: pMeOf / pMeArz / qTitMeOf / qTitMeArz / zOrdMeOf / zOrdMeArz
بر اساس نگاشت رسمی pytse-client/common.py
"""

import requests
import sqlite3
import time
from datetime import datetime

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


def fetch_order_book(ins_code=None, max_retries=3):
    ins_code = ins_code or config.INS_CODE
    url = f"https://cdn.tsetmc.com/api/BestLimits/{ins_code}"
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
        except requests.exceptions.RequestException as e:
            print("ORDER-BOOK CONNECTION ERROR:", e)
            time.sleep(2)
            continue
        if response.status_code != 200:
            print("ORDER-BOOK SERVER ERROR:", response.status_code)
            time.sleep(2)
            continue
        if not response.text or not response.text.strip():
            print(f"ORDER-BOOK EMPTY RESPONSE (attempt {attempt}/{max_retries}) -> RETRYING")
            time.sleep(2)
            continue
        try:
            data = response.json()
        except ValueError:
            print("ORDER-BOOK INVALID JSON:", response.text[:300])
            time.sleep(2)
            continue
        levels = data.get("bestLimitsInfo") or data.get("bestLimits") or data.get("bestLimitsData")
        if not levels:
            # اگر ساختار متفاوت بود، کلیدها را چاپ کن تا دیباگ شود
            print("ORDER-BOOK UNEXPECTED RESPONSE SHAPE -- کلیدها:", list(data.keys()) if isinstance(data, dict) else type(data))
            print("نمونه داده:", str(data)[:500])
            return None
        return levels
    print("ORDER-BOOK FAILED AFTER", max_retries, "ATTEMPTS")
    return None


def _ensure_table(cur):
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
    cur.execute("PRAGMA table_info(order_book)")
    existing = {r[1] for r in cur.fetchall()}
    required = {
        "time": "TEXT", "level": "INTEGER", "buy_count": "INTEGER",
        "buy_volume": "REAL", "buy_price": "REAL", "sell_price": "REAL",
        "sell_volume": "REAL", "sell_count": "INTEGER",
    }
    for col, coltype in required.items():
        if col not in existing:
            try:
                cur.execute(f"ALTER TABLE order_book ADD COLUMN {col} {coltype}")
            except Exception as e:
                print(f"⚠️ ORDER-BOOK WARNING: نتونستم ستون '{col}' رو اضافه کنم: {e}")


def _get_field(lv, *names):
    for n in names:
        if n in lv and lv[n] is not None:
            try:
                # بعضی API ها رشته برمی‌گردانند
                return lv[n]
            except Exception:
                return lv[n]
    return 0


def collect_order_book(db_path=None, ins_code=None):
    """عمق سفارش رو می‌گیره، توی دیتابیس ذخیره می‌کنه، و خلاصه تحلیلی برمی‌گردونه."""
    db_path = db_path or config.DATABASE_NAME
    levels = fetch_order_book(ins_code=ins_code)
    if not levels:
        return None

    rows = []
    for lv in levels:
        try:
            # نگاشت درست بر اساس pytse-client:
            # bid = pMeDem / qTitMeDem / zOrdMeDem
            # ask = pMeOf / qTitMeOf / zOrdMeOf  (و همچنین pMeArz/qTitMeArz/zOrdMeArz به عنوان fallback)
            level = int(_get_field(lv, "number", "depth", "level") or 0)
            buy_cnt = int(float(_get_field(lv, "zOrdMeDem", "buyOrderCount", "buy_count") or 0))
            buy_vol = float(_get_field(lv, "qTitMeDem", "buyVolume", "buy_volume") or 0)
            buy_price = float(_get_field(lv, "pMeDem", "buyPrice", "buy_price") or 0)

            sell_price = float(_get_field(lv, "pMeOf", "pMeOf", "pMeArz", "pMeArz", "sellPrice", "sell_price", "ask") or 0)
            sell_vol = float(_get_field(lv, "qTitMeOf", "qTitMeOf", "qTitMeArz", "qTitMeArz", "sellVolume", "sell_volume", "vol_ask") or 0)
            sell_cnt = int(float(_get_field(lv, "zOrdMeOf", "zOrdMeOf", "zOrdMeArz", "zOrdMeArz", "sellOrderCount", "sell_count", "num_ask") or 0))

            # اگر هر دو قیمت صفر بود، احتمالاً فیلدها متفاوت است - یک بار کلیدها را چاپ کن
            if buy_price == 0 and sell_price == 0 and len(rows) == 0:
                print("⚠️ DEBUG اولین ردیف خام:", lv)

            rows.append((level, buy_cnt, buy_vol, buy_price, sell_price, sell_vol, sell_cnt))
        except Exception as e:
            print(f"ORDER-BOOK ROW PARSE ERROR: {e} -- lv={lv}")
            continue

    if not rows:
        print("ORDER-BOOK: هیچ ردیف قابل‌پردازشی نبود -- نمونه:", levels[:1] if levels else None)
        return None

    rows.sort(key=lambda r: r[0])

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        _ensure_table(cur)
        for level, bc, bv, bp, sp, sv, sc in rows:
            cur.execute(
                "INSERT INTO order_book(time, level, buy_count, buy_volume, buy_price, "
                "sell_price, sell_volume, sell_count) VALUES (?,?,?,?,?,?,?,?)",
                (now, level, bc, bv, bp, sp, sv, sc),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print("ORDER-BOOK DB ERROR:", e)

    total_buy_vol = sum(r[2] for r in rows)
    total_sell_vol = sum(r[5] for r in rows)
    total_buy_cnt = sum(r[1] for r in rows)
    total_sell_cnt = sum(r[6] for r in rows)
    best_buy = rows[0][3] if rows else None
    best_sell = rows[0][4] if rows else None
    spread = (best_sell - best_buy) if (best_buy and best_sell and best_buy>0 and best_sell>0) else None
    spread_pct = round((spread / best_buy) * 100, 3) if (spread and best_buy) else None

    buy_side_empty = (best_buy in (None, 0)) and total_buy_vol == 0 and total_buy_cnt == 0
    sell_side_empty = (best_sell in (None, 0)) and total_sell_vol == 0 and total_sell_cnt == 0

    if buy_side_empty and not sell_side_empty:
        print("⚠️ ORDER-BOOK WARNING: سمت خرید کاملاً صفره ولی سمت فروش داده داره -- "
              "ممکنه صف فروش واقعی باشه، یا ممکنه TSETMC اسم فیلدهای خرید رو عوض کرده باشه "
              "(دقیقاً همون باگ pMeOf ولی این‌بار سمت خرید). کلیدهای ردیف خام برای چک:", levels[0] if levels else None)
    elif sell_side_empty and not buy_side_empty:
        print("⚠️ ORDER-BOOK WARNING: سمت فروش کاملاً صفره ولی سمت خرید داده داره -- "
              "ممکنه صف خرید واقعی باشه، یا ممکنه نگاشت فیلد فروش دوباره عوض شده باشه. "
              "کلیدهای ردیف خام برای چک:", levels[0] if levels else None)

    if buy_side_empty and sell_side_empty:
        market_state = "NO_DATA"
    elif sell_side_empty and not buy_side_empty:
        market_state = "LOCKED_BUY_QUEUE"
    elif buy_side_empty and not sell_side_empty:
        market_state = "LOCKED_SELL_QUEUE"
    else:
        market_state = "TWO_SIDED"

    imbalance = None
    if market_state == "TWO_SIDED" and (total_buy_vol + total_sell_vol) > 0:
        imbalance = round(
            (total_buy_vol - total_sell_vol) / (total_buy_vol + total_sell_vol) * 100, 1
        )

    if market_state in ("LOCKED_BUY_QUEUE", "LOCKED_SELL_QUEUE", "NO_DATA"):
        pressure = market_state
    elif imbalance is None:
        pressure = "UNKNOWN"
    elif imbalance > 20:
        pressure = "BUY_HEAVY"
    elif imbalance < -20:
        pressure = "SELL_HEAVY"
    else:
        pressure = "BALANCED"

    return {
        "time": now,
        "best_buy": best_buy,
        "best_sell": best_sell,
        "spread": spread,
        "spread_pct": spread_pct,
        "total_buy_volume": total_buy_vol,
        "total_sell_volume": total_sell_vol,
        "total_buy_count": total_buy_cnt,
        "total_sell_count": total_sell_cnt,
        "market_state": market_state,
        "imbalance_pct": imbalance,
        "pressure": pressure,
        "levels": rows,
    }


if __name__ == "__main__":
    result = collect_order_book()
    if result:
        print("=" * 50)
        print("عمق سفارش (تابلوخوانی زنده) - نسخه فیکس 2026-08-31")
        print("=" * 50)
        print(f"وضعیت بازار: {result['market_state']}")
        print(f"بهترین خرید: {result['best_buy']} | بهترین فروش: {result['best_sell']}")
        print(f"اسپرد: {result['spread']} ({result['spread_pct']}%)")
        print(f"حجم صف خرید (۵ ردیف): {result['total_buy_volume']:,.0f}")
        print(f"حجم صف فروش (۵ ردیف): {result['total_sell_volume']:,.0f}")
        print(f"بایاس: {result['imbalance_pct']}% -> {result['pressure']}")
        print("\nجزئیات 5 ردیف:")
        for lv in result['levels']:
            print(f"  level={lv[0]} buy={lv[3]} vol={lv[2]} cnt={lv[1]} | sell={lv[4]} vol={lv[5]} cnt={lv[6]}")
    else:
        print("داده‌ای دریافت نشد -- پیام‌های بالا رو برای من بفرست تا فیلدها رو اصلاح کنم.")