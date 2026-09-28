# -*- coding: utf-8 -*-
"""
جستجوی امن (بدون مشکل انکودینگ ویندوز) برای پیدا کردن خط‌های مربوط به
مدت‌زمان هر سیکل، تو فایل لاگ. نتیجه رو تو یه فایل متنی می‌نویسه.

اجرا:
    python find_cycle_time.py logs\ahram_pro_2026-09-22.log
"""
import sys
import glob

MARKER = "\u0637\u0648\u0644 \u06a9\u0634\u06cc\u062f"  # "طول کشید"
OUTPUT_FILE = "cycle_time_result.txt"


def main():
    if len(sys.argv) >= 2:
        paths = [sys.argv[1]]
    else:
        paths = sorted(glob.glob("logs/*.log"))
        if not paths:
            paths = sorted(glob.glob("*.log"))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        if not paths:
            out.write("هیچ فایل لاگی پیدا نشد. مسیر رو دستی به‌عنوان آرگومان بده.\n")
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                out.write(f"فایل پیدا نشد: {path}\n")
                continue

            matches = [ln for ln in lines if MARKER in ln]
            out.write(f"\n{'=' * 60}\n")
            out.write(f"فایل: {path}\n")
            out.write(f"تعداد خط پیدا‌شده: {len(matches)}\n")
            out.write(f"{'=' * 60}\n")
            for ln in matches:
                out.write(ln)

    print(f"نتیجه تو فایل {OUTPUT_FILE} نوشته شد -- اونو با Notepad باز کن و برام بفرست.")


if __name__ == "__main__":
    main()