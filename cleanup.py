# -*- coding: utf-8 -*-
"""
================================================================
  🧹  پاکسازی پروژه — انتقال فایل‌های تستی/اضافی به _archive
================================================================
  چیزی حذف نمی‌شود؛ فقط فایل‌های تستی به پوشه‌ی _archive منتقل
  می‌شوند تا قابل برگشت باشند.

  اجرا:   python cleanup.py
================================================================
"""
import os
import sys
import shutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FOLDER = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(FOLDER, "_archive")

# فایل‌های اصلی ربات — هرگز لمس نمی‌شوند
CORE = {
    # === هسته اصلی ===
    "agent.py", "config.py", "strategy.py", "database.py", "collector.py",
    "signal_generator.py", "ahram_signal.py",
    
    # === آپشن ===
    "option_engine.py", "option_selector.py", "option_decision.py",
    "option_collector.py", "option_order_book.py",
    "spread_strategy.py",
    
    # === اندیکاتورها ===
    "ichimoku.py", "vwap.py", "price_action.py", "market_regime.py",
    "heikin_ashi.py", "multi_timeframe.py", "bollinger.py", "rsi.py",
    "ema.py", "macd.py", "adx.py", "candle_builder.py",
    "fibonacci.py", "rsi_divergence.py",
    
    # === فیلترها ===
    "fog_meter.py", "tape_reader.py", "queue_surge.py",
    
    # === یادگیری ماشین ===
    "learning_core.py",
    
    # === داشبورد و اعلان ===
    "dashboard.py", "desktop_notify.py",
    "telegram_notify.py", "telegram_config.py",
    
    # === دیتا و ابزار ===
    "index_feed.py", "money_flow.py", "history_loader.py",
    "symbols_utils.py", "symbols_setup.py",
    
    # === فایل‌های اجرایی ===
    "start.bat", "start_ahram.bat",
}


def is_obvious_test(name):
    """فقط فایل‌های قطعاً تستی رو تشخیص می‌ده."""
    n = name.lower()
    if name in CORE or name == "cleanup.py":
        return False
    if not n.endswith(".py"):
        return False
    if n.startswith("test_") or n.endswith("_test.py"):
        return True
    if n.startswith("backtest"):
        return True
    if n.startswith("check_") or n.startswith("debug_"):
        return True
    if n.startswith("fix_") or n.startswith("patch_"):
        return True
    if n.startswith("export_") or n.startswith("clean_"):
        return True
    if n.startswith("clear_") or n.startswith("revert_"):
        return True
    if n.startswith("find_") or n.startswith("get_"):
        return True
    if n.startswith("list_"):
        return True
    return False


def main():
    print("=" * 60)
    print("🧹  پاکسازی پروژه")
    print("=" * 60)

    files = sorted(
        f for f in os.listdir(FOLDER)
        if os.path.isfile(os.path.join(FOLDER, f))
    )
    core_files = [f for f in files if f in CORE]
    test_files = [f for f in files if is_obvious_test(f)]
    other_files = [
        f for f in files
        if f not in CORE and not is_obvious_test(f) and f != "cleanup.py"
    ]

    print("\n✅ فایل‌های اصلی ربات (نگه داشته می‌شون):")
    for f in core_files:
        print("    ", f)
    if not core_files:
        print("    (هیچ‌کدوم پیدا نشد!)")

    print("\n🧪 فایل‌های تستی/اضافی (به _archive منتقل می‌شون):")
    for f in test_files:
        print("    ", f)
    if not test_files:
        print("    (چیزی پیدا نشد)")

    print("\n❓ بقیه‌ی فایل‌ها:")
    for f in other_files:
        print("    ", f)
    if not other_files:
        print("    (چیزی نیست)")

    if not test_files:
        print("\n" + "-" * 60)
        print("چیزی برای جابجایی نبود.")
        return

    os.makedirs(ARCHIVE, exist_ok=True)
    print("\n" + "-" * 60)
    print("در حال انتقال فایل‌های تستی به _archive ...")
    for f in test_files:
        src = os.path.join(FOLDER, f)
        dst = os.path.join(ARCHIVE, f)
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(src, dst)
        print("    ✅", f)

    print("\n" + "=" * 60)
    print("✅ تمام!")
    print("=" * 60)


if __name__ == "__main__":
    main()