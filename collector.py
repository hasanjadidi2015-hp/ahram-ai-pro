# -*- coding: utf-8 -*-
"""collector.py — دریافت قیمت زنده‌ی سهم از TSETMC"""
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


def fetch_closing_price(max_retries=3):
    url = (
        f"https://cdn.tsetmc.com/api/"
        f"ClosingPrice/GetClosingPriceInfo/"
        f"{config.INS_CODE}"
    )
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
        except requests.exceptions.RequestException as e:
            print("CONNECTION ERROR:", e)
            time.sleep(2)
            continue
        if response.status_code != 200:
            print("SERVER ERROR :", response.status_code)
            time.sleep(2)
            continue
        if not response.text or not response.text.strip():
            print(f"EMPTY RESPONSE (attempt {attempt}/{max_retries}) -> RETRYING")
            time.sleep(2)
            continue
        try:
            data = response.json()
        except ValueError:
            print(f"INVALID JSON (attempt {attempt}/{max_retries}) -> RETRYING")
            print("RAW RESPONSE:", response.text[:200])
            time.sleep(2)
            continue
        closing_info = data.get("closingPriceInfo")
        if not closing_info:
            print("UNEXPECTED RESPONSE SHAPE:", data)
            return None
        return closing_info
    print("FAILED TO FETCH DATA AFTER", max_retries, "ATTEMPTS")
    return None


def collect():
    data = fetch_closing_price()
    if data is None:
        return
    try:
        last_price = data["pDrCotVal"]
        closing_price = data["pClosing"]
        volume = data["qTotTran5J"]
        trades = data["zTotTran"]
    except KeyError as e:
        print("MISSING FIELD IN RESPONSE:", e)
        return

    conn = sqlite3.connect(config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_price, volume, trades FROM prices ORDER BY id DESC LIMIT 1"
    )
    last = cursor.fetchone()
    if last:
        old_price, old_volume, old_trades = last
        if old_price == last_price and old_volume == volume and old_trades == trades:
            print("DUPLICATE DATA -> SKIPPED")
            conn.close()
            return
    cursor.execute(
        """
        INSERT INTO prices (time, last_price, closing_price, volume, trades)
        VALUES (?,?,?,?,?)
        """,
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         last_price, closing_price, volume, trades)
    )
    conn.commit()
    conn.close()

    print("=" * 40)
    print("NEW DATA SAVED")
    print("=" * 40)
    print("PRICE  :", last_price)
    print("CLOSE  :", closing_price)
    print("VOLUME :", volume)
    print("TRADES :", trades)


if __name__ == "__main__":
    collect()