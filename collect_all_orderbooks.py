# -*- coding: utf-8 -*-
"""
کالکتور و ادغام‌کننده همه نمادها - نسخه 2026-08-31 V2
کار:
1. بک‌آپ از V5 ها می‌گیرد (هیچوقت اصلی‌ها را پاک نمی‌کند)
2. تاریخچه order_book اصلی (815 ردیف درست) را داخل V5 کپی می‌کند (فقط ردیف‌های جدید)
3. لایو جدید برای هر 6 دیتابیس می‌گیرد

اجرا: python collect_all_orderbooks.py
بعدش: python check_order_book.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import sqlite3
import shutil
import os
from datetime import datetime
from order_book import collect_order_book

# اصلی‌ها - هرگز پاک نشوند
SYMBOLS_MAIN = [
    ("اهرم", "ahram_v2.db", "17914401175772326"),
    ("وبملت", "webmellt.db", "778253364357513"),
    ("شستا", "shasta.db", "2400322364771558"),
]

# V5 ها - باید با اصلی ادغام شوند
SYMBOLS_V5 = [
    ("اهرم V5", "ahram_v2_v5.db", "17914401175772326"),
    ("وبملت V5", "webmellt_v5.db", "778253364357513"),
    ("شستا V5", "shasta_v5.db", "2400322364771558"),
]

# نگاشت اصلی -> V5 برای ادغام
MERGE_MAP = [
    ("ahram_v2.db", "ahram_v2_v5.db"),
    ("webmellt.db", "webmellt_v5.db"),
    ("shasta.db", "shasta_v5.db"),
]

def backup_db(db_path):
    if not os.path.exists(db_path):
        print(f"⚠️ {db_path} وجود ندارد - بک‌آپ لازم نیست")
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{db_path}.backup_{ts}"
    try:
        shutil.copy2(db_path, backup_name)
        print(f"💾 بک‌آپ گرفته شد: {backup_name}")
    except Exception as e:
        print(f"❌ بک‌آپ {db_path} خطا: {e}")

def ensure_order_book_table(db_path):
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
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
    conn.commit()
    conn.close()

def merge_main_into_v5(main_db, v5_db):
    if not os.path.exists(main_db):
        print(f"⚠️ اصلی {main_db} نیست - ادغام نمی‌شود")
        return 0
    if not os.path.exists(v5_db):
        print(f"⚠️ V5 {v5_db} نیست - از اصلی کپی می‌شود")
        try:
            shutil.copy2(main_db, v5_db)
            print(f"✅ {main_db} -> {v5_db} کپی کامل شد")
            return 9999
        except Exception as e:
            print(f"❌ کپی خطا: {e}")
            return 0

    ensure_order_book_table(v5_db)
    ensure_order_book_table(main_db)

    conn_main = sqlite3.connect(main_db)
    cur_main = conn_main.cursor()
    conn_v5 = sqlite3.connect(v5_db)
    cur_v5 = conn_v5.cursor()

    try:
        cur_main.execute("SELECT time, level, buy_count, buy_volume, buy_price, sell_price, sell_volume, sell_count FROM order_book ORDER BY time, level")
        rows_main = cur_main.fetchall()
    except Exception as e:
        print(f"❌ خواندن {main_db} خطا: {e}")
        conn_main.close()
        conn_v5.close()
        return 0

    try:
        cur_v5.execute("SELECT time, level FROM order_book")
        existing = set((r[0], r[1]) for r in cur_v5.fetchall())
    except Exception as e:
        existing = set()
        print(f"⚠️ خواندن V5 {v5_db} خطا: {e} - همه ردیف‌ها جدید فرض می‌شود")

    new_count = 0
    for r in rows_main:
        key = (r[0], r[1])  # time + level
        if key not in existing:
            cur_v5.execute("INSERT INTO order_book(time, level, buy_count, buy_volume, buy_price, sell_price, sell_volume, sell_count) VALUES (?,?,?,?,?,?,?,?)", r)
            new_count += 1
            existing.add(key)

    conn_v5.commit()
    conn_main.close()
    conn_v5.close()
    print(f"🔄 ادغام {main_db} -> {v5_db}: {new_count} ردیف جدید از {len(rows_main)} ردیف اصلی اضافه شد")
    return new_count

print("="*60)
print("مرحله 1: بک‌آپ V5 ها")
print("="*60)
for _, v5_db, _ in SYMBOLS_V5:
    backup_db(v5_db)

print("\n" + "="*60)
print("مرحله 2: ادغام تاریخچه اصلی -> V5")
print("="*60)
for main_db, v5_db in MERGE_MAP:
    merge_main_into_v5(main_db, v5_db)

print("\n" + "="*60)
print("مرحله 3: جمع‌آوری لایو جدید برای هر 6 دیتابیس")
print("="*60)

ALL_SYMBOLS = SYMBOLS_MAIN + SYMBOLS_V5

for name, db, ins in ALL_SYMBOLS:
    print(f"\n{'='*50}")
    print(f"📊 جمع‌آوری {name} - {db} - {ins}")
    try:
        result = collect_order_book(db_path=db, ins_code=ins)
        if result:
            print(f"✅ {name}: {result['market_state']} | buy={result['best_buy']} sell={result['best_sell']} | buy_vol={result['total_buy_volume']:,.0f} sell_vol={result['total_sell_volume']:,.0f} | بایاس={result['imbalance_pct']}% {result['pressure']}")
        else:
            print(f"❌ {name}: داده نگرفت")
    except Exception as e:
        print(f"❌ خطا {name}: {e}")
        import traceback; traceback.print_exc()

print("\n✅ تمام شد")
print("حالا بزن: python check_order_book.py")
print("بعدش: python dashboard.py و python dashboard_v5.py")
