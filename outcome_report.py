# -*- coding: utf-8 -*-
"""
گزارش نتایج معاملات -- فقط خواندنی، هیچ چیزی رو تغییر نمی‌ده.
فقط معاملات بعد از ۲۵ مهر ۱۴۰۵ (۲۰۲۶-۱۰-۱۷) شمرده می‌شن.
هر پوزیشن یک‌بار شمرده می‌شه، با آخرین وضعیت قطعی‌اش.

اجرا (کنار فایل‌های .db پروژه):
    python outcome_report.py
خروجی روی صفحه + فایل outcome_report.txt
"""
import os
import sqlite3

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
START_DATE = "2026-10-17"   # ۲۵ مهر ۱۴۰۵
MIN_TRADES = 30             # حداقل معامله‌ی قابل اتکا برای هر نماد
ZERO_BAND = 0.5             # قدر مطلق درصد کمتر از این = سربه‌سر (۰٪)
OUT = "outcome_report.txt"

FINAL_SQL = """
WITH ranked AS (
    SELECT position_id, signal_type, outcome, outcome_pct, id,
           ROW_NUMBER() OVER (PARTITION BY position_id ORDER BY id DESC) AS rn
    FROM signal_history
    WHERE position_id IS NOT NULL
      AND signal_type IN ('BUY_CALL', 'BUY_PUT')
      AND outcome IN ('WIN', 'LOSS', 'BREAK_EVEN')
      AND time >= ?
)
SELECT signal_type, outcome, outcome_pct
FROM ranked
WHERE rn = 1
"""

lines = []


def out(s=""):
    print(s)
    lines.append(str(s))


def split_by_pct(rows):
    wins, losses, zeros, nopct = [], [], [], 0
    for _, _, pct in rows:
        if pct is None:
            nopct += 1
        elif pct > ZERO_BAND:
            wins.append(pct)
        elif pct < -ZERO_BAND:
            losses.append(pct)
        else:
            zeros.append(pct)
    return wins, losses, zeros, nopct


def averages(wins, losses):
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    return avg_w, avg_l


out("=" * 70)
out("گزارش نتایج معاملات (فقط خواندنی) -- از ۲۵ مهر ۱۴۰۵ به بعد")
out("=" * 70)

all_rows = []

for name, db in DBS:
    if not os.path.exists(db):
        out(f"\n⚠️ {db} پیدا نشد -- رد شد")
        continue

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(FINAL_SQL, (START_DATE,)).fetchall()
    finally:
        conn.close()

    all_rows.extend(rows)
    wins, losses, zeros, nopct = split_by_pct(rows)
    n_dec = len(wins) + len(losses)

    out(f"\n--- {name} ({db}) ---")
    out(f"   پوزیشن‌های قطعی: {len(rows)} | برد: {len(wins)} | باخت: {len(losses)} | "
        f"سربه‌سر ۰٪: {len(zeros)} | بی‌درصد: {nopct}")

    if not rows:
        out("   هیچ معامله‌ای بعد از ۲۵ مهر پیدا نشد")
        continue

    avg_w, avg_l = averages(wins, losses)
    if n_dec:
        ev = (len(wins) / n_dec) * avg_w + (len(losses) / n_dec) * avg_l
        out(f"   میانگین سود برنده: {avg_w:.2f}٪ | میانگین زیان بازنده: {avg_l:.2f}٪")
        out(f"   امید ریاضی (بدون ۰٪ ها): {ev:.2f}٪")
    if n_dec < MIN_TRADES:
        out(f"   ⚠️ کمتر از {MIN_TRADES} معامله‌ی قطعی؛ این عدد قابل اتکا نیست")

# ---------- جمع کل ----------
out("\n" + "=" * 70)
out("جمع کل همه‌ی نمادها:")

wins, losses, zeros, nopct = split_by_pct(all_rows)
n_dec = len(wins) + len(losses)
out(f"   پوزیشن‌های قطعی: {len(all_rows)} | برد: {len(wins)} | باخت: {len(losses)} | "
    f"سربه‌سر ۰٪: {len(zeros)} | بی‌درصد: {nopct}")

if n_dec:
    avg_w, avg_l = averages(wins, losses)
    n_pess = n_dec + len(zeros)
    ev_opt = (len(wins) / n_dec) * avg_w + (len(losses) / n_dec) * avg_l
    ev_pess = (len(wins) / n_pess) * avg_w + ((len(losses) + len(zeros)) / n_pess) * avg_l

    out(f"   میانگین سود برنده: {avg_w:.2f}٪ | میانگین زیان بازنده: {avg_l:.2f}٪")
    out(f"   نرخ برد: {len(wins) / n_dec * 100:.1f}٪")
    out(f"   امید ریاضی خوش‌بینانه (۰٪ ها کنار): {ev_opt:.2f}٪")
    out(f"   امید ریاضی بدبینانه (۰٪ ها زیان): {ev_pess:.2f}٪")
    if n_dec < MIN_TRADES * 3:
        out("   ⚠️ تعداد کل معاملات قطعی کم است؛ هنوز برای تصمیم کافی نیست")
else:
    out("   معامله‌ی قطعی بعد از ۲۵ مهر وجود ندارد")

out("\nتوجه: معاملات INCONCLUSIVE (داده‌ی قدیمی) و PENDING در محاسبه نیستند.")
out("توجه: سربه‌سر ۰٪ ها ممکن است زیان واقعی باشند؛ دو حالت بالا این بازه را نشان می‌دهد.")
out("=" * 70)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nنتیجه در فایل {OUT} ذخیره شد -- اونو برام بفرست.")