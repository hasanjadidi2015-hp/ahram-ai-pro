"""
AHRAM AI PRO - Max Pain (Exploratory / Phase 1)

این ماژول فقط Max Pain را محاسبه و در دیتابیس ذخیره می‌کند.
هیچ اثری روی سیگنال، امتیاز، اطمینان یا تصمیم معاملاتی ندارد.
"""

import argparse
import json
import math
import os
import sqlite3
from datetime import datetime


DEFAULT_DATABASES = ["ahram_v2.db", "webmellt.db", "shasta.db"]


def _safe_float(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _create_history_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS max_pain_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            latest_options_time TEXT,
            underlying_symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            stock_price REAL,
            max_pain_strike REAL,
            current_distance_pct REAL,
            total_pain REAL,
            contracts_count INTEGER NOT NULL DEFAULT 0,
            contracts_with_oi INTEGER NOT NULL DEFAULT 0,
            data_quality TEXT NOT NULL,
            candidate_strikes TEXT,
            details TEXT
        )
        """
    )
    connection.commit()


def calculate_max_pain(rows):
    """محاسبه Max Pain از رکوردهای یک snapshot و یک سررسید."""
    contracts = []
    stock_prices = []

    for row in rows:
        option_type = str(row["option_type"] or "").upper().strip()
        strike = _safe_float(row["strike_price"])
        open_interest = _safe_float(row["open_interest"])
        stock_price = _safe_float(row["stock_price"])

        if strike is None or strike <= 0:
            continue
        if stock_price is not None and stock_price > 0:
            stock_prices.append(stock_price)
        if option_type not in ("CALL", "PUT"):
            continue
        if open_interest is None or open_interest < 0:
            open_interest = 0.0

        contracts.append(
            {
                "option_type": option_type,
                "strike": strike,
                "open_interest": open_interest,
            }
        )

    if not contracts:
        return None

    stock_price = stock_prices[0] if stock_prices else None
    strikes = sorted({item["strike"] for item in contracts})
    pains = {}

    for settlement in strikes:
        total_pain = 0.0
        for contract in contracts:
            if contract["option_type"] == "CALL":
                intrinsic = max(settlement - contract["strike"], 0.0)
            else:
                intrinsic = max(contract["strike"] - settlement, 0.0)
            total_pain += intrinsic * contract["open_interest"]
        pains[settlement] = total_pain

    max_pain_strike = min(pains, key=pains.get)
    oi_contracts = sum(1 for item in contracts if item["open_interest"] > 0)

    if oi_contracts >= 10 and len(strikes) >= 5:
        quality = "HIGH"
    elif oi_contracts >= 5 and len(strikes) >= 3:
        quality = "MEDIUM"
    else:
        quality = "LOW"

    distance_pct = None
    if stock_price and stock_price > 0:
        distance_pct = ((stock_price - max_pain_strike) / stock_price) * 100.0

    ranked = sorted(pains.items(), key=lambda item: item[1])[:3]

    return {
        "stock_price": stock_price,
        "max_pain_strike": max_pain_strike,
        "current_distance_pct": distance_pct,
        "total_pain": pains[max_pain_strike],
        "contracts_count": len(contracts),
        "contracts_with_oi": oi_contracts,
        "data_quality": quality,
        "candidate_strikes": [strike for strike, _ in ranked],
        "pain_by_strike": {str(strike): pain for strike, pain in pains.items()},
    }


def analyze_database(db_path, save=True):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    latest_time_row = connection.execute(
        "SELECT MAX(time) AS latest_time FROM options"
    ).fetchone()
    latest_time = latest_time_row["latest_time"] if latest_time_row else None

    if not latest_time:
        connection.close()
        return []

    # قیمت سهم از جدول prices خوانده می‌شود؛ این جدول منبع اصلی قیمت underlying است.
    price_row = connection.execute(
        "SELECT last_price, closing_price FROM prices ORDER BY id DESC LIMIT 1"
    ).fetchone()
    current_stock_price = None
    if price_row:
        current_stock_price = _safe_float(price_row["last_price"])
        if current_stock_price is None or current_stock_price <= 0:
            current_stock_price = _safe_float(price_row["closing_price"])

    rows = connection.execute(
        """
        SELECT symbol, option_type, stock_price, strike_price,
               expire_date, open_interest, time
        FROM options
        WHERE time = ?
          AND expire_date IS NOT NULL
          AND TRIM(expire_date) <> ''
        ORDER BY expire_date, strike_price
        """,
        (latest_time,),
    ).fetchall()

    grouped = {}
    for row in rows:
        expiry = str(row["expire_date"]).strip()
        grouped.setdefault(expiry, []).append(row)

    results = []
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    underlying_symbol = os.path.splitext(os.path.basename(db_path))[0]

    for expiry, expiry_rows in sorted(grouped.items()):
        result = calculate_max_pain(expiry_rows)
        if not result:
            continue

        # اگر options.stock_price خالی باشد، قیمت جدول prices جایگزین می‌شود.
        if current_stock_price is not None and current_stock_price > 0:
            result["stock_price"] = current_stock_price
            result["current_distance_pct"] = (
                (current_stock_price - result["max_pain_strike"])
                / current_stock_price
            ) * 100.0

        result["underlying_symbol"] = underlying_symbol
        result["expiry"] = expiry
        result["latest_options_time"] = latest_time
        result["time"] = run_time
        results.append(result)

        if save:
            _create_history_table(connection)
            connection.execute(
                """
                INSERT INTO max_pain_history (
                    time, latest_options_time, underlying_symbol, expiry,
                    stock_price, max_pain_strike, current_distance_pct,
                    total_pain, contracts_count, contracts_with_oi,
                    data_quality, candidate_strikes, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_time,
                    latest_time,
                    underlying_symbol,
                    expiry,
                    result["stock_price"],
                    result["max_pain_strike"],
                    result["current_distance_pct"],
                    result["total_pain"],
                    result["contracts_count"],
                    result["contracts_with_oi"],
                    result["data_quality"],
                    json.dumps(result["candidate_strikes"], ensure_ascii=False),
                    json.dumps(result["pain_by_strike"], ensure_ascii=False),
                ),
            )

    if save:
        connection.commit()
    connection.close()
    return results


def print_results(db_path, results):
    print("\n" + "=" * 72)
    print("MAX PAIN |", os.path.basename(db_path))
    if not results:
        print("NO DATA")
        return

    for result in results:
        distance = result["current_distance_pct"]
        distance_text = "N/A" if distance is None else f"{distance:+.2f}%"
        print(
            f"EXPIRY: {result['expiry']} | "
            f"MAX PAIN: {result['max_pain_strike']:g} | "
            f"STOCK: {result['stock_price']} | "
            f"DISTANCE: {distance_text} | "
            f"QUALITY: {result['data_quality']} | "
            f"OI: {result['contracts_with_oi']}/{result['contracts_count']}"
        )
        print("TOP 3 LOWEST PAIN STRIKES:", result["candidate_strikes"])


def main():
    parser = argparse.ArgumentParser(description="Exploratory Max Pain calculator")
    parser.add_argument("databases", nargs="*", default=DEFAULT_DATABASES)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    for db_path in args.databases:
        if not os.path.exists(db_path):
            print(f"SKIPPED: database not found: {db_path}")
            continue
        results = analyze_database(db_path, save=not args.no_save)
        print_results(db_path, results)


if __name__ == "__main__":
    main()
