# -*- coding: utf-8 -*-
"""
ابزار تشخیصی 100% فقط‌خواندنی برای پیدا کردن دقیق باگ‌های dashboard.py
هیچ فایلی تغییر داده نمی‌شود.
"""
import os
import sqlite3
import re

DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db"
}

print("\n" + "="*70)
print("🔍 گام ۱: بررسی کد dashboard.py — از چه ستون‌هایی می‌خواند؟")
print("="*70)

if os.path.exists("dashboard.py"):
    with open("dashboard.py", "r", encoding="utf-8") as f:
        code = f.read()
    
    # جستجوی نام ستون‌هایی که کد استفاده می‌کند
    patterns_found = []
    for keyword in ["score", "composite_score", "signal_type", "option_symbol",
                    "option_price", "stop_loss", "target1", "target2", "take_profit",
                    "qty", "outcome"]:
        matches = re.findall(rf'["\']?\b{keyword}\b["\']?', code)
        if matches:
            patterns_found.append((keyword, len(matches)))
    
    print(f"\n📄 ستون‌هایی که در dashboard.py استفاده می‌شوند:")
    for name, cnt in patterns_found:
        print(f"   • {name}: {cnt} بار")
else:
    print("❌ فایل dashboard.py یافت نشد!")

print("\n" + "="*70)
print("🔍 گام ۲: مقایسه با دیتابیس واقعی — چه چیزی در آخرین رکورد هست؟")
print("="*70)

for sym, db in DBS.items():
    print(f"\n📊 دیتابیس: [{db}] برای نماد [{sym}]")
    print("-" * 70)
    
    if not os.path.exists(db):
        print(f"⚠️ فایل پیدا نشد.")
        continue
    
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # آخرین رکورد signal_history
        cur.execute("SELECT * FROM signal_history ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        
        if row:
            d = dict(row)
            print(f"   ✅ آخرین سیگنال (id={d.get('id')}) در {d.get('time')}:")
            important_cols = ["signal_type", "composite_score", "option_symbol",
                              "option_price", "stop_loss", "target1", "target2",
                              "outcome", "outcome_pct"]
            for col in important_cols:
                val = d.get(col, "❓ ستون وجود ندارد")
                marker = "✅" if val not in [None, "", "❓ ستون وجود ندارد"] else "⚠️"
                print(f"      {marker} {col:20s} = {val}")
        else:
            print("   ⚠️ هیچ سیگنالی ثبت نشده.")
    
    except Exception as e:
        print(f"   ❌ خطا: {e}")
    finally:
        conn.close()

print("\n" + "="*70)
print("🔍 گام ۳: تست شبیه‌سازی — کد dashboard.py الان چه خروجی می‌سازد؟")
print("="*70)

# شبیه‌سازی همان کاری که dashboard.py می‌کند
for sym, db in DBS.items():
    if not os.path.exists(db):
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM signal_history ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            d = dict(row)
            # این دقیقاً کاری است که dashboard.py می‌کند (طبق کد قبلی من)
            score_read_v1 = d.get("score", 0.0)          # ❌ اشتباه من - این ستون وجود ندارد
            score_read_v2 = d.get("composite_score", 0)  # ✅ درست
            tp_read_v1 = d.get("take_profit", "-")       # ❌ اشتباه من
            tp_read_v2 = d.get("target1", "-")           # ✅ درست
            
            print(f"\n[{sym}]")
            print(f"   اگر کد از 'score' بخواند       → {score_read_v1}  ← احتمالاً همین باگ است!")
            print(f"   اگر کد از 'composite_score' بخواند → {score_read_v2}  ← این عدد درست است")
            print(f"   اگر کد از 'take_profit' بخواند    → {tp_read_v1}  ← احتمالاً همین باگ است!")
            print(f"   اگر کد از 'target1' بخواند        → {tp_read_v2}  ← این عدد درست است")
    except Exception as e:
        print(f"   ❌ {e}")
    finally:
        conn.close()

print("\n" + "="*70)
print("✅ تشخیص کامل شد. نتیجه بالا را برای اصلاح دقیق بفرستید.")
print("="*70 + "\n")