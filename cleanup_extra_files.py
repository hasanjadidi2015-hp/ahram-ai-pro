# -*- coding: utf-8 -*-
"""
پاک‌سازی فایل‌های اضافه/تکراری/بی‌استفاده از پوشه‌ی پروژه.
فقط فایل‌هایی که مطمئنیم اضافه‌ان پاک می‌شن؛ اگه فایلی وجود نداشته باشه
(مثلاً قبلاً پاک شده)، بدون خطا رد می‌شه.

اجرا:
    python cleanup_extra_files.py
"""
import os

FILES_TO_DELETE = [
    # خروجی HTML قدیمی که دیگه هیچ کدی بهش نمی‌نویسه (dashboard_v5.py الان
    # به‌جاش options_dashboard_VIP5.html می‌سازه)
    "dashboard_VIP5.html",

    # کپی دقیق create_v5_dbs.py با پسوند اشتباه (.p به‌جای .py)
    "create_v5_dbs.p",

    # بک‌آپ‌های قدیمی‌تر (2026-08-31) که نسخه‌ی جدیدترشون (2026-09-01)
    # همه‌ی داده‌شون رو هم داره -- یعنی دیگه اضافه‌ان
    "ahram_v2_v5.db.backup_20260831_204354",
    "shasta_v5.db.backup_20260831_204354",
    "webmellt_v5.db.backup_20260831_204354",
]

deleted = []
not_found = []

for fname in FILES_TO_DELETE:
    if os.path.exists(fname):
        os.remove(fname)
        deleted.append(fname)
    else:
        not_found.append(fname)

print("=" * 50)
print(f"✅ پاک شد ({len(deleted)} فایل):")
for f in deleted:
    print(f"   - {f}")

if not_found:
    print(f"\nℹ️ از قبل وجود نداشت ({len(not_found)} فایل):")
    for f in not_found:
        print(f"   - {f}")
print("=" * 50)