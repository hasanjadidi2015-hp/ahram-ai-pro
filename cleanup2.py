# -*- coding: utf-8 -*-
"""
================================================================
  🧹  پاکسازی مرحله‌ی ۲ — فایل‌های آزمایشی/قدیمیِ باقی‌مونده
================================================================
  همه‌ی فایل‌های .py که ربات بهشون نیاز نداره رو به _archive
  می‌بره. بعد **خودش** چک می‌کنه که agent.py بدون مشکل اجرا
  می‌شه یا نه. اگه فایلی لازم بوده، خودش برش می‌گردونه.

  چیزی حذف نمی‌شه؛ فقط جابجا می‌شه.
  فایل‌های داده (.db, .json, .html, .txt) دست‌نخورده می‌مونن.

  اجرا:   python cleanup2.py
================================================================
"""
import os
import sys
import shutil
import subprocess
import re

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FOLDER = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(FOLDER, "_archive")

# فایل‌های اصلی ربات — هرگز لمس نمی‌شن
CORE = {
    "agent.py", "config.py", "strategy.py",
    "option_engine.py", "option_selector.py", "option_decision.py",
    "option_collector.py", "option_order_book.py",
    "signal_generator.py", "learning_core.py", "dashboard.py",
    "symbols_utils.py", "symbols_setup.py",
    "collector.py", "database.py",
    "ichimoku.py", "vwap.py", "price_action.py", "market_regime.py",
    "heikin_ashi.py", "multi_timeframe.py", "bollinger.py", "rsi.py",
    "candle_builder.py",
    "desktop_notify.py", "telegram_notify.py", "telegram_config.py",
    "index_feed.py", "money_flow.py",
    "ahram_signal.py",
    "start.bat",
}

# این‌ها هم نگه داشته می‌شن (ابزار مفید / خود اسکریپت)
SPECIAL_KEEP = {"history_loader.py", "cleanup.py", "cleanup2.py", "requirements.txt"}


def check_agent_import():
    """آیا `import agent` بدون خطا انجام می‌شه؟
    خروجی: (اوکی؟, نام_ماژول_گمشده یا None, متن_خطا)"""
    r = subprocess.run(
        [sys.executable, "-c", "import agent"],
        cwd=FOLDER, capture_output=True, text=True,
    )
    if r.returncode == 0:
        return True, None, ""
    err = r.stderr or r.stdout
    m = re.search(r"No module named ['\"](\w+)['\"]", err)
    missing = m.group(1) if m else None
    return False, missing, err


def main():
    os.makedirs(ARCHIVE, exist_ok=True)

    all_items = sorted(os.listdir(FOLDER))
    to_archive = []
    kept_py = []
    data_files = []

    for f in all_items:
        path = os.path.join(FOLDER, f)
        if not os.path.isfile(path):
            continue                       # پوشه‌ها رو ول کن
        low = f.lower()
        if not low.endswith(".py"):
            data_files.append(f)           # فایل غیر-Py (داده) — دست‌نخورده
            continue
        if f in CORE or f in SPECIAL_KEEP:
            kept_py.append(f)
        else:
            to_archive.append(f)

    print("=" * 60)
    print("🧹  پاکسازی مرحله‌ی ۲")
    print("=" * 60)

    print("\n✅ فایل‌های .py که نگه داشته می‌شن:")
    for f in kept_py:
        print("    ", f)

    print(f"\n📦 فایل‌های .py برای انتقال به _archive: {len(to_archive)}")
    for f in to_archive:
        print("    ", f)

    print(f"\n💾 فایل‌های داده (دست‌نخورده می‌مونن): {len(data_files)}")

    if not to_archive:
        print("\nچیزی برای جابجایی نیست.")
        return

    # انتقال به _archive
    print("\n" + "-" * 60)
    print("در حال انتقال...")
    moved = []
    for f in to_archive:
        src = os.path.join(FOLDER, f)
        dst = os.path.join(ARCHIVE, f)
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(src, dst)
        moved.append(f)
    print(f"  {len(moved)} فایل منتقل شد.")

    # بررسی: آیا agent.py سرپاست؟
    print("\n" + "-" * 60)
    print("🔍 بررسی: آیا agent.py بدون مشکل لود می‌شه؟")
    restored = []
    for _ in range(30):
        ok, missing, err = check_agent_import()
        if ok:
            print("  ✅ agent.py مشکلی نداره — همه‌چیز سرپاست.")
            break
        # اگه ماژول گمشده، یک فایل محلی تو آرشیو هست → برگردونش
        arch = os.path.join(ARCHIVE, missing + ".py") if missing else None
        if missing and arch and os.path.exists(arch):
            shutil.move(arch, os.path.join(FOLDER, missing + ".py"))
            restored.append(missing + ".py")
            print(f"  ⚠️ «{missing}.py» لازم بود → برگردونده شد.")
            continue
        # خطای غیرمنتظره (مثلاً کتابخونه‌ی pip) → همه رو برگردون
        print("  ❌ خطایی غیر از کمبود فایل محلی رخ داد:")
        print("    ", err.strip().splitlines()[-1] if err.strip() else "?")
        print("  → برای اطمینان همه‌چیز برگردونده می‌شه.")
        for f in moved:
            a = os.path.join(ARCHIVE, f)
            if os.path.exists(a):
                shutil.move(a, os.path.join(FOLDER, f))
        print("  همه‌چیز برگشت. وضعیت مثل قبلِ اجراست.")
        return
    else:
        print("  تعداد تلاش‌ها زیاد شد؛ متوقف شد.")

    print("\n" + "=" * 60)
    print("✅ تموم شد!")
    print(f"   منتقل‌شده به _archive: {len(moved) - len(restored)} فایل")
    if restored:
        print(f"   برگردونده‌شده (لازم بودن): {', '.join(restored)}")
    print()
    print("   حالا تست نهایی:")
    print("       python agent.py")
    print()
    print("   اگه درست کار کرد، می‌تونی بعداً پوشه‌ی _archive رو")
    print("   هم پاک کنی.")
    print("=" * 60)


if __name__ == "__main__":
    main()