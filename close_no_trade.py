# -*- coding: utf-8 -*-
"""
بستن پوزیشن‌های بازِ «بدون معامله» با برچسب NO_TRADE (مثل طملت9041).

پوزیشن بدون معامله: در دو روز معاملاتی آخری که در جدول options ثبت شده (یعنی جدیدترین
دو تاریخ)، هیچ ردیفی برای قراردادش حجم یا تعداد معامله‌ی بیشتر از صفر نداشته. چنین قراردادی
در این مدت قابل معامله نبوده، پس سود/زیانش واقعی نیست و نباید در ارزیابی بیاید.
(نسخه‌ی قبلی از زمان ورود می‌سنجید؛ آن قاعده قراردادهایی را که چند روز پیش معامله شده بودند
ولی الان نه، پیدا نمی‌کرد، مثل طملت9041.)

اجرا (کنار فایل‌های .db، با ربات بسته):
    python close_no_trade.py            <- فقط نشان می‌دهد چه چیزی تغییر می‌کند (هیچ تغییری نمی‌دهد)
    python close_no_trade.py --apply    <- اول از دیتابیس نسخه‌ی پشتیبان می‌گیرد، بعد تغییر می‌دهد
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

DBS = [("اهرم", "ahram_v2.db"), ("وبملت", "webmellt.db"), ("شستا", "shasta.db")]
APPLY = "--apply" in sys.argv

OPEN_SQL = """
SELECT s.position_id, s.option_symbol, s.option_price, s.time
FROM signal_history s
JOIN (SELECT position_id, MIN(id) AS mid FROM signal_history
      WHERE outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL GROUP BY position_id) m
  ON s.id = m.mid
"""

print("=" * 60)
print("حالت: " + ("اعمال تغییر (با پشتیبان)" if APPLY else "فقط پیش‌نمایش (هیچ چیز تغییر نمی‌کند)"))
print("=" * 60)

total = 0
for name, db in DBS:
    if not os.path.exists(db):
        print(f"{name}: {db} پیدا نشد")
        continue

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(options)")}
    if not ({"volume", "trades_count"} <= cols):
        print(f"{name}: ستون‌های حجم/تعداد معاملات هنوز در options نیست (یک بار ربات یا option_collector را اجرا کنید)")
        conn.close()
        continue

    # اگر جمع‌آوری آپشن از چند روز پیش متوقف شده، داده‌ی آخر قدیمی است و قضاوت درست نیست
    newest = conn.execute("SELECT MAX(time) FROM options").fetchone()[0]
    from datetime import timedelta
    min_ok_day = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    if not newest or str(newest)[:10] < min_ok_day:
        print(f"{name}: آخرین ثبت options ({newest}) قدیمی است؛ جمع‌آوری کار نکرده، قضاوت نمی‌شود")
        conn.close()
        continue

    # پنجره: از اولین روز از دو روز معاملاتی آخری که در options ثبت شده
    days = [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(time,1,10) FROM options ORDER BY 1 DESC LIMIT 2").fetchall()]
    if not days:
        print(f"{name}: جدول options خالی است")
        conn.close()
        continue
    window_start = min(days) + " 00:00:00"

    # اگر در این پنجره هیچ قراردادی از این دیتابیس ثبت نشده، جمع‌آوری کار نکرده؛ هیچ قضاوتی نمی‌کنیم
    total_rows = conn.execute(
        "SELECT COUNT(*) FROM options WHERE time>=?", (window_start,)).fetchone()[0]
    if total_rows == 0:
        print(f"{name}: در پنجره‌ی {min(days)} تا {max(days)} هیچ ردیفی ثبت نشده؛ قضاوت نمی‌شود")
        conn.close()
        continue

    targets = []
    report = []
    for pid, sym, entry, t0 in conn.execute(OPEN_SQL).fetchall():
        max_vol, max_trades, n_rows = conn.execute(
            "SELECT MAX(COALESCE(volume,0)), MAX(COALESCE(trades_count,0)), COUNT(*) "
            "FROM options WHERE symbol=? AND time>=?",
            (sym, window_start),
        ).fetchone()
        # بی‌معامله: یا همه‌ی ردیف‌های پنجره حجم صفر دارند، یا اصلاً ردیفی ندارد
        # (جمع‌آوری قیمت صفر را ثبت نمی‌کند، پس نبود ردیف یعنی قیمت و معامله‌ای نبوده)
        no_trade = (n_rows == 0) or ((max_vol or 0) == 0 and (max_trades or 0) == 0)
        report.append((sym, entry, t0, n_rows, max_vol or 0, max_trades or 0, no_trade))
        if no_trade:
            targets.append((pid, sym, entry, t0, n_rows))

    print(f"\n--- {name} ({db}) | پوزیشن بدون معامله: {len(targets)} ---")
    print(f"   پنجره‌ی بررسی: {min(days)} تا {max(days)}")
    for sym, entry, t0, n_rows, mv, mt, nt in report:
        mark = "بی‌معامله" if nt else "معامله‌دار"
        print(f"   {sym} | ورود {entry} در {t0} | ردیف در پنجره: {n_rows} | بیشترین حجم: {mv:.0f} | تعداد معامله: {mt:.0f} | {mark}")

    if targets and APPLY:
        backup = f"{db}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        conn.close()
        shutil.copy2(db, backup)
        print(f"   نسخه‌ی پشتیبان: {backup}")
        conn = sqlite3.connect(db)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for pid, sym, entry, t0, n_rows in targets:
            conn.execute(
                "UPDATE signal_history SET outcome='NO_TRADE', outcome_pct=NULL, outcome_time=? "
                "WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                (now, pid),
            )
        conn.commit()
        print(f"   ✅ {len(targets)} پوزیشن با برچسب NO_TRADE بسته شد")
    total += len(targets)
    conn.close()

print("\n" + "=" * 60)
if total == 0:
    print("پوزیشن بدون معامله‌ای پیدا نشد.")
elif not APPLY:
    print(f"{total} پوزیشن پیدا شد. برای اعمال: python close_no_trade.py --apply")
print("=" * 60)