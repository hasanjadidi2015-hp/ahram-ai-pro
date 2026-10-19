# -*- coding: utf-8 -*-
"""
خروجی کامل دیتای جمع‌شده‌ی رباط به CSV (فقط خواندنی، هیچ دیتایی تغییر نمی‌کنه).

- همه‌ی جدول‌های ahram_v2.db / webmellt.db / shasta.db و نسخه‌های *_v5.db
- هر جدول یک فایل CSV جدا
- فایل index.txt با تعداد ردیف و بازه‌ی زمانی هر جدول
- در آخر یک فایل ZIP از کل خروجی

اجرا (کنار فایل‌های .db پروژه):
    python export_all_data.py
"""
import csv
import glob
import os
import shutil
import sqlite3
from datetime import datetime

STAMP = datetime.now().strftime("%Y%m%d_%H%M")
OUT_DIR = f"export_data_{STAMP}"
MAIN_DBS = ["ahram_v2.db", "webmellt.db", "shasta.db"]


def list_dbs():
    dbs = []
    for d in MAIN_DBS:
        if os.path.exists(d):
            dbs.append(d)
    for d in sorted(glob.glob("*_v5.db")):
        if ".backup" not in d and d not in dbs:
            dbs.append(d)
    return dbs


def time_range(cur, table):
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if "time" not in cols:
        return "-"
    try:
        mn, mx = cur.execute(f"SELECT MIN(time), MAX(time) FROM {table}").fetchone()
        return f"{mn} تا {mx}"
    except Exception:
        return "-"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    index_lines = [f"خروجی دیتا -- {STAMP}", "=" * 70]
    total_rows = 0
    dbs = list_dbs()
    if not dbs:
        print("هیچ فایل .db پیدا نشد. این فایل را کنار دیتابیس‌ها اجرا کن.")
        return

    for db in dbs:
        stem = os.path.splitext(db)[0]
        index_lines.append(f"\n## {db}")
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except Exception as e:
            index_lines.append(f"  ❌ باز نشد: {e}")
            continue
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()]
        for table in tables:
            try:
                cursor = conn.execute(f"SELECT * FROM {table}")
                headers = [d[0] for d in cursor.description]
                fname = os.path.join(OUT_DIR, f"{stem}__{table}.csv")
                n = 0
                with open(fname, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    for row in cursor:
                        w.writerow(row)
                        n += 1
                total_rows += n
                index_lines.append(f"  {table:22s} | {n:7d} ردیف | {time_range(cur, table)}")
            except Exception as e:
                index_lines.append(f"  ❌ {table}: خطا در خواندن: {e}")
        conn.close()

    index_lines.append("\n" + "=" * 70)
    index_lines.append(f"جمع کل ردیف‌ها: {total_rows}")
    with open(os.path.join(OUT_DIR, "index.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))

    zip_path = shutil.make_archive(OUT_DIR, "zip", OUT_DIR)
    print("\n".join(index_lines))
    print(f"\nزیپ آماده شد: {zip_path}")
    print("فایل زیپ رو برای من آپلود کن (یا اگه خیلی بزرگه، فقط index.txt رو بفرست).")


if __name__ == "__main__":
    main()