# -*- coding: utf-8 -*-
"""
AHRAM SYMBOLS SETUP - تاریخچه‌ی نمادهای جدید را بارگذاری می‌کند.
روش اجرا:  python symbols_setup.py
"""
import sys
import sqlite3
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config
from database import create_database
from symbols_utils import resolve_ins_code

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.tsetmc.com/"}


def load_history(name, ins_code, db_name):
    config.DATABASE_NAME = db_name
    create_database()
    url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{ins_code}/0"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"  ❌ سرور خطا داد: {r.status_code}")
            return 0
        data = r.json().get("closingPriceDaily", [])
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        return 0
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()
    count = 0
    for row in reversed(data):
        try:
            cur.execute("""INSERT INTO prices (time, last_price, closing_price, volume, trades)
                           VALUES (?,?,?,?,?)""",
                        (str(row["dEven"]), row["pDrCotVal"], row["pClosing"],
                         row["qTotTran5J"], row["zTotTran"]))
            count += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return count


def main():
    print("=" * 60)
    print("AHRAM SYMBOLS SETUP - راه‌اندازی نمادها")
    print("=" * 60)
    for sym in config.SYMBOLS:
        name = sym["name"]
        db = sym.get("db", "ahram_v2.db")
        ins = sym.get("ins_code", "")
        print(f"\n📌 نماد: {name}")
        if not ins:
            print(f"  در حال پیدا کردن کد از TSETMC...")
            ins = resolve_ins_code(name)
            if not ins:
                print(f"  ❌ کد {name} پیدا نشد.")
                continue
            print(f"  ✅ کد پیدا شد: {ins}")
        print(f"  در حال بارگذاری تاریخچه...")
        n = load_history(name, ins, db)
        print(f"  ✅ {n} روز تاریخچه در {db} ذخیره شد.")
    print("\n" + "=" * 60)
    print("✅ راه‌اندازی کامل شد.")
    print("=" * 60)


if __name__ == "__main__":
    main()