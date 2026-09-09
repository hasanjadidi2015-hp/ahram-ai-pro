# -*- coding: utf-8 -*-
"""
جستجوی امن (بدون مشکل انکودینگ ویندوز) برای پیدا کردن یه رشته‌ی خاص تو
فایل‌های HTML بزرگ داشبورد. نتیجه رو تو یه فایل متنی می‌نویسه (نه رو
کنسول) تا مشکل نمایش فارسی تو cmd/PowerShell پیش نیاد.

اجرا:
    python find_in_dashboard.py options_dashboard_AHRAM_LIVE5.html
"""
import sys

SEARCH_TERM = "\u0636\u0645\u0644\u062a7045"  # ضملت7045 -- به‌صورت کد یونیکد نوشته شده تا تو خودِ اسکریپت هم مشکلی پیش نیاد
SEARCH_TERM_ESCAPED = "".join(f"\\u{ord(c):04x}" for c in SEARCH_TERM[:4]) + SEARCH_TERM[4:]
# حالت دوم: همون رشته ولی به شکل اسکیپ‌شده‌ی JSON (\u0636\u0645\u0644\u062a7045)
# -- چون بعضی جاهای فایل ممکنه با json.dumps(ensure_ascii=True) ساخته شده باشن
CONTEXT_CHARS = 400
OUTPUT_FILE = "find_result.txt"


def main():
    if len(sys.argv) < 2:
        print("استفاده: python find_in_dashboard.py <اسم فایل HTML>")
        return

    html_path = sys.argv[1]
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    all_hits = []
    for term, label in [(SEARCH_TERM, "متن مستقیم فارسی"), (SEARCH_TERM_ESCAPED, "فرم اسکیپ‌شده \\u...")]:
        start = 0
        while True:
            idx = content.find(term, start)
            if idx == -1:
                break
            all_hits.append((idx, label))
            start = idx + 1

    all_hits.sort()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(f"تعداد دفعاتی که پیدا شد: {len(all_hits)}\n")
        out.write("=" * 70 + "\n")
        for i, (idx, label) in enumerate(all_hits):
            s = max(0, idx - CONTEXT_CHARS)
            e = min(len(content), idx + CONTEXT_CHARS)
            out.write(f"\n--- مورد {i+1} ({label}, موقعیت کاراکتر {idx}) ---\n")
            out.write(content[s:e])
            out.write("\n")

    print(f"نتیجه تو فایل {OUTPUT_FILE} نوشته شد -- اونو با Notepad باز کن و برام بفرست.")


if __name__ == "__main__":
    main()