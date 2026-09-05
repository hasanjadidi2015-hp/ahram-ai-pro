# -*- coding: utf-8 -*-
"""
ابزار تشخیصی فقط‌خواندنی (Read-Only) برای بررسی سازگاری دیتابیس واقعی با option_selector
تاریخ: 2026-09-02
"""

import os
import sys
import sqlite3
import glob

# ایمپورت کردن تابع انتخاب آپشن از فایلی که در مرحله ۱ ساختیم
try:
    from option_selector import get_best_option
except ImportError:
    print("❌ خطا: فایل option_selector.py در این پوشه پیدا نشد.")
    sys.exit(1)


def inspect_database(db_path: str):
    """بررسی ساختار جدول آپشن‌ها در دیتابیس واقعی"""
    print(f"\n{'='*60}")
    print(f"📊 در حال بررسی دیتابیس: {db_path}")
    print(f"{'='*60}")

    if not os.path.exists(db_path):
        print(f"⚠️ فایل {db_path} وجود ندارد.")
        return

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) # اتصال فقط‌خواندنی (کاملاً ایمن)
    cursor = conn.cursor()

    try:
        # ۱. پیدا کردن نام تمام جدول‌های موجود در دیتابیس
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"📁 جدول‌های موجود در دیتابیس: {', '.join(tables)}")

        # پیدا کردن جدولی که به آپشن‌ها مربوط است
        target_table = None
        for candidate in ['options_data', 'options', 'option_chain', 'options_history']:
            if candidate in tables:
                target_table = candidate
                break

        if not target_table:
            print("⚠️ جدول اختصاصی آپشن‌ها با نام‌های استاندارد پیدا نشد.")
            return

        print(f"✅ جدول آپشن‌ها پیدا شد: [{target_table}]")

        # ۲. نمایش ستون‌های جدول
        cursor.execute(f"PRAGMA table_info({target_table})")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"📋 ستون‌های جدول: {', '.join(columns)}")

        # ۳. نمایش تعداد کل رکوردهای آپشن
        cursor.execute(f"SELECT COUNT(*) FROM {target_table}")
        count = cursor.fetchone()[0]
        print(f"🔢 تعداد رکوردهای ثبت‌شده آپشن: {count}")

        # ۴. نمایش یک نمونه رکورد واقعی برای اطمینان
        cursor.execute(f"SELECT * FROM {target_table} LIMIT 1")
        sample = cursor.fetchone()
        if sample:
            print("\n🔍 نمونه یک داده واقعی:")
            for col, val in zip(columns, sample):
                print(f"   • {col}: {val}")

        # ۵. دریافت آخرین قیمت دارایی پایه (اگر جدول قیمت وجود دارد)
        ua_price = 55500.0 # قیمت پیش‌فرض اهرم
        if 'prices' in tables:
            try:
                cursor.execute("SELECT last_price, closing_price FROM prices ORDER BY id DESC LIMIT 1")
                price_row = cursor.fetchone()
                if price_row:
                    ua_price = float(price_row[0] or price_row[1] or 55500.0)
                    print(f"\n📈 آخرین قیمت ثبت‌شده دارایی پایه: {ua_price:,.0f} ریال")
            except Exception:
                pass

        # ۶. تست واقعی انتخاب آپشن با دیتابیس واقعی!
        print("\n🎯 تست خروجی واقعی `option_selector` روی این دیتابیس:")
        
        print("\n  [تست خرید CALL بر اساس قیمت فعلی]")
        best_call = get_best_option(db_path, "اهرم", "BUY_CALL", ua_price)
        if best_call:
            print(f"  🟢 بهترین CALL یافت شد: {best_call.get('symbol')} | اعمال: {best_call.get('strike_price_clean')} | سررسید: {best_call.get('dte_clean')} روز")
        else:
            print("  ⚪ برای CALL آپشنی با شرایط فیلترها (اسپرد و DTE) پیدا نشد.")

        print("\n  [تست خرید PUT بر اساس قیمت فعلی]")
        best_put = get_best_option(db_path, "اهرم", "BUY_PUT", ua_price)
        if best_put:
            print(f"  🔴 بهترین PUT یافت شد: {best_put.get('symbol')} | اعمال: {best_put.get('strike_price_clean')} | سررسید: {best_put.get('dte_clean')} روز")
        else:
            print("  ⚪ برای PUT آپشنی با شرایط فیلترها (اسپرد و DTE) پیدا نشد.")

    except Exception as e:
        print(f"❌ خطای غیرمنتظره در بررسی دیتابیس: {e}")
    finally:
        conn.close()


def main():
    print("\n🔍 جستجوی تمام فایل‌های دیتابیس در پوشه جاری...")
    # بررسی دیتابیس‌های اصلی که در داکیومنت معرفی شده بودند
    main_dbs = ['ahram_v2.db', 'webmellt.db', 'shasta.db']
    
    found_any = False
    for db in main_dbs:
        if os.path.exists(db):
            found_any = True
            inspect_database(db)

    # اگر هیچ‌کدام پیدا نشد، هر دیتابیس موجود با پسوند .db را چک کن
    if not found_any:
        all_dbs = glob.glob("*.db")
        if all_dbs:
            for db in all_dbs:
                inspect_database(db)
        else:
            print("⚠️ هیچ فایل دیتابیسی (*.db) در پوشه جاری پیدا نشد.")


if __name__ == "__main__":
    main()