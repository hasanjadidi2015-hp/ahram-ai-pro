# -*- coding: utf-8 -*-
"""
ابزار پرتابل باز کردن داشبوردهای زنده سیستم بدون سردرگمی
نسخه اصلاحی — فقط داشبوردهای ساخت خودمان
"""
import os
import sys
import webbrowser

DASHBOARDS = {
    "1": ("dashboard.html", "داشبورد موتور V4 (ساده، سیگنال‌های متنی)"),
    "2": ("dashboard_v5.html", "داشبورد موتور V5 (تم دارک VIP)")
}

def main():
    print("\n" + "="*60)
    print("👑 به سامانه مدیریت داشبوردهای Ahram AI خوش آمدید")
    print("="*60)
    print("کدام داشبورد را می‌خواهید در مرورگر باز کنید؟")
    for key, (filename, desc) in DASHBOARDS.items():
        status = "🟢 موجود" if os.path.exists(filename) else "❌ ناموجود"
        print(f"  [{key}] {desc}\n      └─ فایل: {filename} ({status})")
    print("="*60)
    
    choice = input("عدد گزینه مورد نظر را وارد کنید (مثلا 1): ").strip()
    
    if choice in DASHBOARDS:
        filename, desc = DASHBOARDS[choice]
        if os.path.exists(filename):
            full_path = 'file:///' + os.path.abspath(filename)
            webbrowser.open(full_path)
            print(f"\n✅ {desc} با موفقیت در مرورگر شما باز شد.")
        else:
            print(f"\n❌ خطا: فایل {filename} هنوز ساخته نشده است.")
            print("   ابتدا دستور 'python dashboard.py' یا 'python dashboard_v5.py' را اجرا کنید.")
    else:
        print("\n❌ انتخاب نامعتبر. لطفاً عدد 1 یا 2 را وارد کنید.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()