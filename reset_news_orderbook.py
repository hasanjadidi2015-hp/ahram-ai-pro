# -*- coding: utf-8 -*-
"""
پاک‌سازی امن داده‌های آزمایشی خبر و Order Book.

این فایل:
- daily_news را پاک می‌کند
- news_settings را پاک می‌کند تا Baseline دوباره ساخته شود
- جدول قدیمی order_book را حذف می‌کند تا با ساختار جدید ساخته شود

این فایل به prices، options، signal_history، ML و سایر داده‌های اصلی دست نمی‌زند.
"""

import os
import sqlite3

DATABASES = [
    "ahram_v2.db",
    "webmellt.db",
    "shasta.db",
]


def reset_database(db_path):
    if not os.path.exists(db_path):
        print(f"[SKIP] فایل پیدا نشد: {db_path}")
        return

    print(f"\n{'=' * 60}")
    print(f"در حال اصلاح: {db_path}")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # پاک‌سازی خبرهای قبلی
    cur.execute("DROP TABLE IF EXISTS daily_news")
    print("✅ جدول daily_news حذف شد")

    # پاک‌سازی وضعیت baseline قبلی
    cur.execute("DROP TABLE IF EXISTS news_settings")
    print("✅ جدول news_settings حذف شد")

    # حذف ساختار قدیمی عمق سفارش
    cur.execute("DROP TABLE IF EXISTS order_book")
    print("✅ جدول order_book قدیمی حذف شد")

    conn.commit()
    conn.close()

    print(f"✅ اصلاح دیتابیس {db_path} تمام شد")


def main():
    print("=" * 60)
    print("RESET NEWS + ORDER BOOK")
    print("=" * 60)
    print("هشدار: فقط داده‌های خبر و Order Book پاک می‌شوند.")
    print("قیمت‌ها، آپشن‌ها، سیگنال‌ها و مدل ML دست‌نخورده می‌مانند.")

    for db in DATABASES:
        try:
            reset_database(db)
        except Exception as e:
            print(f"❌ خطا در {db}: {e}")

    print("\n" + "=" * 60)
    print("✅ عملیات تمام شد.")
    print("اکنون می‌توانی ربات را یک‌بار اجرا کنی.")
    print("=" * 60)


if __name__ == "__main__":
    main()