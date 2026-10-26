# -*- coding: utf-8 -*-
"""
تشخیص فیلدهای خام یک قرارداد از MarketWatchInit (فقط خواندنی، هیچ چیزی ذخیره نمی‌شود).
اجرا (کنار config.py):
    python diagnose_option_fields.py 9028
خروجی: همه‌ی فیلدهای خام هر قراردادی که شماره‌ی داده‌شده در نماد یا نامش باشد، با اندیس.
"""
import sys

import requests

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.tsetmc.com/",
}


def fetch_instruments():
    r = requests.get(config.MARKET_WATCH_URL, headers=HEADERS, timeout=25)
    parts = r.text.strip().split("@")
    if len(parts) < 3:
        sys.exit(f"فرمت غیرمنتظره‌ی پاسخ (تعداد بخش‌ها: {len(parts)})")
    return parts[2].strip().split(";")


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "9028"
    items = fetch_instruments()
    matched = 0
    for item in items:
        f = item.split(",")
        if len(f) < 3:
            continue
        symbol = f[2].strip()
        name = f[3].strip() if len(f) > 3 else ""
        if key not in symbol and key not in name:
            continue
        matched += 1
        print("=" * 70)
        print(f"نماد: {symbol} | نام: {name} | تعداد فیلد: {len(f)}")
        for idx, val in enumerate(f):
            print(f"   [{idx:2d}] {val.strip()}")
    if matched == 0:
        print(f"هیچ قراردادی با «{key}» در پاسخ پیدا نشد")
    else:
        print(f"\nتعداد قرارداد پیداشده: {matched}")


if __name__ == "__main__":
    main()