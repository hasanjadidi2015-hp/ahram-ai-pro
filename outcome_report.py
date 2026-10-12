# -*- coding: utf-8 -*-
"""
گزارش سه‌ماهه‌ی نتایج معاملات -- فقط خواندنی، هیچ چیزی رو تغییر نمی‌ده.
اجرا (کنار فایل‌های .db پروژه):
    python outcome_report.py
خروجی روی صفحه + فایل outcome_report.txt
"""
import sqlite3
import os
from collections import defaultdict

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
OUT = "outcome_report.txt"
lines = []

def out(s=""):
    print(s)
    lines.append(str(s))

out("=" * 70)
out("گزارش نتایج معاملات (فقط خواندنی)")
out("=" * 70)

grand = defaultdict(lambda: [0, 0.0])  # outcome -> [count, sum_pct]

for name, db in DBS:
    if not os.path.exists(db):
        out(f"\n⚠️ {db} پیدا نشد -- رد شد")
        continue
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = conn.cursor()
    out(f"\n--- {name} ({db}) ---")

    cur.execute("""
        SELECT signal_type, COALESCE(outcome,'NULL'), COUNT(DISTINCT position_id),
               COUNT(*), ROUND(AVG(outcome_pct),2), MIN(time), MAX(time)
        FROM signal_history
        WHERE signal_type IN ('BUY_CALL','BUY_PUT') AND position_id IS NOT NULL
        GROUP BY signal_type, outcome ORDER BY signal_type, outcome
    """)
    rows = cur.fetchall()
    if not rows:
        out("   هیچ معامله‌ای (با position_id) پیدا نشد")
    for st, oc, pos_n, rec_n, avg_pct, t0, t1 in rows:
        out(f"   {st:9s} | {oc:10s} | پوزیشن: {pos_n:4d} | رکورد: {rec_n:5d} | "
            f"میانگین ٪: {avg_pct}  | بازه: {str(t0)[:10]} تا {str(t1)[:10]}")
        grand[oc][0] += pos_n
        grand[oc][1] += (avg_pct or 0) * pos_n

    # ریز: پوزیشن‌های سربه‌سر و T1 که بعداً LOSS شدن
    cur.execute("""
        SELECT COUNT(DISTINCT position_id) FROM signal_history
        WHERE outcome='LOSS' AND outcome_pct BETWEEN -0.5 AND 0.5
    """)
    out(f"   ↳ LOSS با ۰٪ (احتمال Break-Even غلط‌برچسب‌خورده): {cur.fetchone()[0]}")

    cur.execute("""
        SELECT COUNT(DISTINCT position_id) FROM signal_history
        WHERE outcome='LOSS' AND position_id IN (
            SELECT position_id FROM signal_history WHERE outcome='T1_HIT' OR (outcome_pct>0)
        )
    """)
    out(f"   ↳ پوزیشن‌هایی که سود داشتن ولی بعداً LOSS شدن (اثر T1): {cur.fetchone()[0]}")
    conn.close()

out("\n" + "=" * 70)
out("جمع کل همه‌ی نمادها (بر اساس پوزیشن):")
for oc, (n, s) in sorted(grand.items()):
    avg = round(s / n, 2) if n else 0
    out(f"   {oc:10s}: {n:5d} پوزیشن | میانگین ٪ ≈ {avg}")

w = grand.get("WIN", [0])[0]
l = grand.get("LOSS", [0])[0]
t1 = grand.get("T1_HIT", [0])[0]
be = grand.get("BREAK_EVEN", [0])[0]
if w + l:
    out(f"\nنرخ برد فعلی (WIN/(WIN+LOSS)): {round(w/(w+l)*100,1)}٪")
    out(f"نرخ برد اگه T1 هم برد حساب بشه: {round((w+t1)/(w+t1+l)*100,1)}٪")
out("=" * 70)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"\nنتیجه در فایل {OUT} ذخیره شد -- اونو برام بفرست.")