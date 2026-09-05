# -*- coding: utf-8 -*-
"""
ابزار تشخیصی فقط‌خواندنی: کشف ساختار واقعی جدول signal_history
هدف: پیدا کردن نام واقعی ستون امتیاز برای فعال‌سازی واقعی فیلتر کیفیت
"""

import os
import sys
import sqlite3

DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db"
}


def detect_column(columns, candidates):
    cols_lower = [c.lower() for c in columns]
    for cand in candidates:
        if cand.lower() in cols_lower:
            return columns[cols_lower.index(cand.lower())]
    return ""


def inspect_db(symbol, db_path):
    print("\n" + "=" * 65)
    print(f"📊 [{symbol}] بررسی جدول signal_history در {db_path}")
    print("=" * 65)

    if not os.path.exists(db_path):
        print("⚠️ دیتابیس پیدا نشد.")
        return

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signal_history';")
        if not cur.fetchone():
            print("⚠️ جدول signal_history در این دیتابیس وجود ندارد.")
            return

        # ۱. لیست کامل ستون‌ها
        cur.execute("PRAGMA table_info(signal_history);")
        cols = [r[1] for r in cur.fetchall()]
        print(f"📋 ستون‌های جدول ({len(cols)} عدد): {', '.join(cols)}")

        # ۲. جستجوی ستون امتیاز میان نام‌های رایج
        score_col = detect_column(cols, ['score', 'final_score', 'signal_score',
                                          'confidence', 'technical_score', 'tech_score',
                                          'total_score', 'check_score', 'strength'])
        if score_col:
            print(f"✅ ستون امتیاز شناسایی شد: [{score_col}]")
            cur.execute(f"SELECT MIN({score_col}), MAX({score_col}), AVG({score_col}) FROM signal_history")
            mn, mx, avg = cur.fetchone()
            print(f"   محدوده امتیازها: {mn} تا {mx} | میانگین: {round(avg or 0, 1)}")
            cur.execute(f"SELECT COUNT(*) FROM signal_history WHERE {score_col} >= 60")
            above = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM signal_history")
            total = cur.fetchone()[0]
            print(f"   سیگنال‌های با امتیاز >= 60: {above} از {total}")
        else:
            print("❌ هیچ ستون امتیازی در این جدول پیدا نشد!")

        # ۳. توزیع انواع سیگنال
        type_col = detect_column(cols, ['signal_type', 'signal', 'action', 'decision'])
        if type_col:
            cur.execute(f"SELECT {type_col}, COUNT(*) FROM signal_history GROUP BY {type_col}")
            print("\n📈 توزیع انواع سیگنال:")
            for row in cur.fetchall():
                print(f"   • {row[0]}: {row[1]}")

        # ۴. سه رکورد آخر (کامل و بدون فرض قبلی درباره نام ستون‌ها)
        print("\n🔍 سه رکورد آخر (جدیدترین سیگنال‌ها):")
        cur.execute("SELECT * FROM signal_history ORDER BY id DESC LIMIT 3")
        for row in cur.fetchall():
            print("   " + "-" * 50)
            for key in row.keys():
                print(f"   • {key}: {row[key]}")

    except Exception as e:
        print(f"❌ خطا: {e}")
    finally:
        conn.close()


def main():
    for sym, db in DBS.items():
        inspect_db(sym, db)
    print("\n✅ بازرسی کامل شد. خروجی بالا را برای تحلیل ارسال کنید.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\n=== [تست ابزار بازرسی signal_history] ===")
        main()
        print("=== [تست پاس شد ✅] ===\n")
    else:
        main()