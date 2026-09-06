# -*- coding: utf-8 -*-
"""
بررسی سریع توابع موجود در موتورهای V5 و Strategy
"""

import inspect

modules_to_check = [
    "strategy",
    "vace_engine_v2",
    "decision_engine_v2",
    "sentiment_engine_v2",
    "contract_scoring_engine_v2"
]

print("\n" + "=" * 65)
print("🔍 بررسی توابع موجود در موتورهای تحلیلی سیستم شما")
print("=" * 65)

for mod_name in modules_to_check:
    try:
        mod = __import__(mod_name)
        funcs = [f[0] for f in inspect.getmembers(mod, inspect.isfunction) if not f[0].startswith('_')]
        classes = [c[0] for c in inspect.getmembers(mod, inspect.isclass) if not c[0].startswith('_')]
        print(f"\n📁 ماژول [{mod_name}]:")
        if funcs:
            print(f"   🔹 توابع: {', '.join(funcs[:10])}")
        if classes:
            print(f"   🔸 کلاس‌ها: {', '.join(classes[:5])}")
    except ImportError:
        print(f"\n❌ ماژول [{mod_name}] یافت نشد.")
    except Exception as e:
        print(f"\n⚠️ خطا در لود [{mod_name}]: {e}")

print("\n" + "=" * 65 + "\n")