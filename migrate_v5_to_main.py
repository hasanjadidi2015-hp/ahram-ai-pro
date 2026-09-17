# -*- coding: utf-8 -*-
"""
مهاجرت یک‌باره‌ی داده‌های V5 به دیتابیس‌های اصلی (V4) -- قبل از ادغام نهایی.

این اسکریپت:
1. اول از هر ۶ دیتابیس بک‌آپ با timestamp می‌گیره (طبق قانون پروژه: هرگز
   بدون بک‌آپ دست به DB نمی‌زنیم)
2. برای جدول‌های "لاگ بازار" (prices, options, order_book, daily_news,
   indices, money_flow, max_pain) هر ردیفی که تو V5 هست ولی تو V4 نیست
   رو کپی می‌کنه -- این کار امنه چون این جدول‌ها فقط لاگ بازارن، به هم
   ریختن ترتیبشون مشکلی ایجاد نمی‌کنه.
3. جدول signal_history (سیگنال‌ها و پوزیشن‌های باز) رو *عمداً* کپی
   نمی‌کنه -- چون از وقتی باگ volume_ok رفع شد، V4 و V5 دارن تقریباً
   دقیقاً همون سیگنال‌ها و پوزیشن‌ها رو جدا از هم می‌سازن. اگه این جدول
   رو هم کپی کنیم، هر پوزیشن واقعی دوبار (یه‌بار با position_id از V4،
   یه‌بار با position_id متفاوت از V5) تو داشبورد نمایش داده می‌شه --
   دقیقاً همون باگ قاطی‌شدن پوزیشن‌ها که قبلاً رفعش کردیم. سیگنال‌ها و
   پوزیشن‌های V4 (که تاریخچه‌ی طولانی‌تری داره) به‌عنوان مرجع اصلی
   نگه داشته می‌شن؛ فایل V5 هرگز پاک نمی‌شه، فقط دیگه ادامه‌ش استفاده
   نمی‌شه (طبق قانون: هیچ دیتابیسی حذف نمی‌شه).

اجرا (فقط یک‌بار، قبل از جایگزینی فایل‌های ادغام‌شده):
    python migrate_v5_to_main.py
"""
import os
import shutil
import sqlite3
from datetime import datetime

# (نام دیتابیس V4 اصلی, نام دیتابیس V5)
DB_PAIRS = [
    ("ahram_v2.db", "ahram_v2_v5.db"),
    ("webmellt.db", "webmellt_v5.db"),
    ("shasta.db", "shasta_v5.db"),
]

# جدول‌هایی که امن هستن برای کپی کامل (فقط لاگ بازار، بدون ریسک قاطی‌شدن پوزیشن)
SAFE_TABLES = ["prices", "options", "order_book", "daily_news", "indices", "money_flow", "max_pain"]

# جدولی که عمداً کپی نمی‌شه (دلیلش بالای فایل توضیح داده شده)
SKIPPED_TABLES = ["signal_history"]


def backup_db(path):
    if not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.backup_{ts}"
    shutil.copy2(path, backup_path)
    print(f"  🛡️ بک‌آپ گرفته شد: {backup_path}")
    return backup_path


def get_columns(conn, table):
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def migrate_table(main_conn, v5_conn, table):
    if not table_exists(v5_conn, table):
        print(f"    - {table}: تو V5 وجود نداره، رد شد")
        return 0
    if not table_exists(main_conn, table):
        print(f"    - {table}: تو V4 اصلی وجود نداره، رد شد (باید دستی بررسی بشه)")
        return 0

    main_cols = set(get_columns(main_conn, table))
    v5_cols = set(get_columns(v5_conn, table))
    # فقط ستون‌های مشترک (به‌جز id که خودکار توسط V4 اختصاص داده می‌شه)
    common_cols = [c for c in v5_cols if c in main_cols and c != "id"]
    if not common_cols:
        print(f"    - {table}: هیچ ستون مشترکی پیدا نشد، رد شد")
        return 0

    dropped = v5_cols - main_cols
    if dropped:
        print(f"    ⚠️ {table}: این ستون‌ها فقط تو V5 بودن و منتقل نمی‌شن: {sorted(dropped)}")

    col_list = ", ".join(common_cols)
    rows = v5_conn.execute(f"SELECT {col_list} FROM {table}").fetchall()
    if not rows:
        print(f"    - {table}: هیچ ردیفی نداشت")
        return 0

    # جلوگیری از تکراری‌شدن: اگه ستون time هست، فقط زمان‌هایی که تو V4 نیستن رو اضافه کن
    inserted = 0
    if "time" in common_cols:
        time_idx = common_cols.index("time")
        existing_times = {r[0] for r in main_conn.execute(f"SELECT DISTINCT time FROM {table}")}
        placeholders = ", ".join("?" for _ in common_cols)
        insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        for row in rows:
            if row[time_idx] not in existing_times:
                main_conn.execute(insert_sql, row)
                inserted += 1
    else:
        # بدون ستون time (نادر) -- همه رو اضافه کن، بهتره از دوباره اجرا کردن
        # این اسکریپت روی همون دیتابیس خودداری بشه
        placeholders = ", ".join("?" for _ in common_cols)
        insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        main_conn.executemany(insert_sql, rows)
        inserted = len(rows)

    print(f"    ✅ {table}: {inserted} ردیف جدید اضافه شد (از {len(rows)} ردیف V5)")
    return inserted


def main():
    print("=" * 70)
    print("🔄 مهاجرت داده‌های V5 به دیتابیس‌های اصلی")
    print("=" * 70)

    for main_db, v5_db in DB_PAIRS:
        print(f"\n📦 {main_db}  <-  {v5_db}")
        if not os.path.exists(main_db):
            print(f"    ❌ {main_db} پیدا نشد، رد شد")
            continue
        if not os.path.exists(v5_db):
            print(f"    ℹ️ {v5_db} پیدا نشد -- شاید قبلاً مهاجرت شده یا اصلاً نبوده. رد شد")
            continue

        backup_db(main_db)

        main_conn = sqlite3.connect(main_db)
        v5_conn = sqlite3.connect(v5_db)
        try:
            total = 0
            for table in SAFE_TABLES:
                total += migrate_table(main_conn, v5_conn, table)
            main_conn.commit()
            print(f"    📊 جمع کل ردیف‌های جدید اضافه‌شده: {total}")

            for table in SKIPPED_TABLES:
                if table_exists(v5_conn, table):
                    cnt = v5_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    print(f"    ℹ️ {table}: عمداً کپی نشد ({cnt} ردیف تو V5 باقی می‌مونه، "
                          f"دیتابیس V5 هم پاک نمی‌شه -- فقط دیگه فعال استفاده نمی‌شه)")
        except Exception as e:
            main_conn.rollback()
            print(f"    ❌ خطا، هیچ تغییری اعمال نشد (rollback شد): {e}")
        finally:
            main_conn.close()
            v5_conn.close()

    print("\n" + "=" * 70)
    print("✅ مهاجرت تمام شد. فایل‌های V5 (_v5.db) دست‌نخورده باقی موندن -- می‌تونی")
    print("   بعداً هر وقت خواستی تاریخچه‌ی سیگنال‌های V5 رو دستی بررسی کنی.")
    print("=" * 70)


if __name__ == "__main__":
    main()