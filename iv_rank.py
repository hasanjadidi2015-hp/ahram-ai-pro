# -*- coding: utf-8 -*-
"""
IV RANK / IV PERCENTILE

IV/HV (توی fog_meter.py) می‌گه نوسان ضمنی نسبت به نوسان واقعی اخیر سهم
چطوره. این ماژول یه چیز متفاوت می‌گه: نوسان ضمنی امروز نسبت به «تاریخچه‌ی
خودش» (روزهای قبل) کجا وایستاده -- که می‌تونه حتی وقتی IV/HV نرماله هم
داغ/سرد بودن غیرعادی رو نشون بده.

  IV Rank = (IV امروز - کمترین IV تاریخچه) / (بیشترین - کمترین) × 100
  IV Percentile = چند درصد روزهای گذشته IV کمتر از امروز بوده

چون پروژه تازه شروع شده، تاریخچه‌ی کافی نداره؛ این ماژول به‌مرور که هر روز
اجرا می‌شه خودش تاریخچه می‌سازه (یه ردیف در روز، از IV آپشن نزدیک ATM که
ربات انتخاب کرده). تا رسیدن به حداقل MIN_DAYS روز داده، خروجی
ready=False برمی‌گرده و نباید بهش اعتماد کرد.
"""
import sqlite3
from datetime import datetime

MIN_DAYS = 10


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            date TEXT PRIMARY KEY,
            atm_iv REAL,
            updated_at TEXT
        )
    """)


def record_daily_iv(db_path, atm_iv):
    """هر سیکل که یه IV معتبر برای آپشن نزدیک ATM داریم صدا زده می‌شه.
    فقط یه ردیف در روز نگه می‌داره (آخرین مقدار همون روز آپدیت می‌شه)،
    چون IV توی روز نوسان می‌کنه و نمی‌خوایم تاریخچه با نمونه‌ی تکراری
    داخل یه روز واحد کج بشه."""
    if not atm_iv or atm_iv <= 0:
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        _ensure_table(cur)
        today = datetime.now().strftime("%Y-%m-%d")
        cur.execute(
            "INSERT INTO iv_history(date, atm_iv, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET atm_iv=excluded.atm_iv, updated_at=excluded.updated_at",
            (today, float(atm_iv), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def compute_iv_rank_percentile(db_path, current_iv=None):
    """
    خروجی:
      iv_rank: (فعلی-کمینه)/(بیشینه-کمینه)×۱۰۰ روی کل تاریخچه‌ی ذخیره‌شده
      iv_percentile: چند درصد روزهای گذشته IV کمتر از امروز بوده
      days: چند روز داده موجوده
      ready: آیا داده کافی برای اعتماد به عدد هست (>= MIN_DAYS)
    """
    empty = {"iv_rank": None, "iv_percentile": None, "days": 0, "ready": False}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        _ensure_table(cur)
        cur.execute("SELECT date, atm_iv FROM iv_history ORDER BY date")
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return empty

    ivs = [r[1] for r in rows if r[1] and r[1] > 0]
    if len(ivs) < 2:
        return {"iv_rank": None, "iv_percentile": None, "days": len(ivs), "ready": False}

    cur_iv = current_iv
    if cur_iv is None:
        today = datetime.now().strftime("%Y-%m-%d")
        today_rows = [r[1] for r in rows if r[0] == today and r[1]]
        cur_iv = today_rows[-1] if today_rows else ivs[-1]

    lo, hi = min(ivs), max(ivs)
    iv_rank = round(((cur_iv - lo) / (hi - lo)) * 100, 1) if hi > lo else 50.0
    below = sum(1 for v in ivs if v < cur_iv)
    iv_percentile = round((below / len(ivs)) * 100, 1)

    return {
        "iv_rank": iv_rank,
        "iv_percentile": iv_percentile,
        "days": len(ivs),
        "ready": len(ivs) >= MIN_DAYS,
    }


if __name__ == "__main__":
    import sys
    import config
    db = sys.argv[1] if len(sys.argv) > 1 else config.DATABASE_NAME
    result = compute_iv_rank_percentile(db)
    print("=" * 40)
    print("IV RANK / IV PERCENTILE")
    print("=" * 40)
    print(f"روزهای موجود: {result['days']} (حداقل لازم: {MIN_DAYS})")
    print(f"آماده: {result['ready']}")
    print(f"IV Rank: {result['iv_rank']}")
    print(f"IV Percentile: {result['iv_percentile']}")