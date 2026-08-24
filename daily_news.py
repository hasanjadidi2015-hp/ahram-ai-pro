# -*- coding: utf-8 -*-
"""
اخبار روزانه -- اطلاعیه‌های بااهمیت کدال + پیام‌های ناظر بازار، هر دو
مخصوص همون نماد، از طریق پروکسی خودِ TSETMC (نه مستقیم از codal.ir).

منابع:
  - کدال (از طریق TSETMC): اطلاعیه‌های بااهمیت گروه الف/ب -- افزایش سرمایه،
    تصمیمات مجمع، قراردادهای مهم و... دقیقاً چیزی که می‌تونه قیمت آپشن رو
    ناگهانی جابه‌جا کنه.
  - پیام‌های ناظر بازار: توقف نماد، هشدار نوسان غیرعادی و مواردی از این دست.

⚠️ هر دو endpoint از یه فهرست معتبر و مستقل از API های TSETMC تأیید شدن
(همون دامنه‌ای که collector.py و option_collector.py هم استفاده می‌کنن)،
ولی اسم دقیق فیلدهای داخل پاسخ رو نتونستم تأیید کنم -- **اولین اجرا رو
حتماً تست کن**. اگه فیلدها فرق داشت، پیام خطا شکل خام پاسخ رو چاپ می‌کنه.
"""
import requests
import sqlite3
import time
from datetime import datetime

import config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
}


def _get_json(url, max_retries=2):
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
        except requests.exceptions.RequestException as e:
            print(f"NEWS CONNECTION ERROR ({url}):", e)
            time.sleep(2)
            continue
        if response.status_code != 200:
            print(f"NEWS SERVER ERROR ({url}):", response.status_code)
            time.sleep(2)
            continue
        if not response.text or not response.text.strip():
            time.sleep(2)
            continue
        try:
            return response.json()
        except ValueError:
            print(f"NEWS INVALID JSON ({url}):", response.text[:300])
            return None
    return None


def fetch_codal_notifications(ins_code=None, top=10):
    """اطلاعیه‌های بااهمیت کدال مخصوص این نماد."""
    ins_code = ins_code or config.INS_CODE
    url = f"https://cdn.tsetmc.com/api/Codal/GetPreparedDataByInsCode/{top}/{ins_code}"
    data = _get_json(url)
    if data is None:
        return []
    items = data if isinstance(data, list) else (
        data.get("codalPreparedData") or data.get("codal") or data.get("data") or []
    )
    if not items:
        print("CODAL NEWS: پاسخ خالی یا شکل ناشناخته:", data)
    return items or []


def fetch_supervisor_messages(ins_code=None, top=10):
    """پیام‌های ناظر بازار (توقف نماد، هشدار و...) مخصوص این نماد."""
    ins_code = ins_code or config.INS_CODE
    url = f"https://cdn.tsetmc.com/api/Msg/GetMsgByInsCode/{ins_code}"
    data = _get_json(url)
    if data is None:
        return []
    items = data if isinstance(data, list) else (
        data.get("insMsg") or data.get("msg") or data.get("data") or []
    )
    if not items:
        print("SUPERVISOR MSG: پاسخ خالی یا شکل ناشناخته:", data)
    return items or []


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            source TEXT,
            item_id TEXT,
            title TEXT,
            raw TEXT,
            price_at_news REAL,
            outcome_pct_1d REAL,
            outcome_pct_5d REAL,
            outcome_pct_20d REAL,
            fully_evaluated INTEGER DEFAULT 0,
            category TEXT
        )
    """)
    # خودترمیم برای دیتابیس‌هایی که این جدول رو از نسخه‌ی قبلی (بدون این
    # ستون‌ها) دارن
    cur.execute("PRAGMA table_info(daily_news)")
    existing = {r[1] for r in cur.fetchall()}
    for col, coltype in [
        ("price_at_news", "REAL"), ("outcome_pct_1d", "REAL"),
        ("outcome_pct_5d", "REAL"), ("outcome_pct_20d", "REAL"),
        ("fully_evaluated", "INTEGER DEFAULT 0"), ("category", "TEXT"),
    ]:
        if col not in existing:
            try:
                cur.execute(f"ALTER TABLE daily_news ADD COLUMN {col} {coltype}")
            except Exception:
                pass


def _current_stock_price(cur):
    cur.execute("SELECT last_price FROM prices WHERE last_price IS NOT NULL AND last_price>0 ORDER BY id DESC LIMIT 1")
    r = cur.fetchone()
    return float(r[0]) if r and r[0] else None


def _extract_title(item):
    for key in ("title", "lTitle", "Title", "subject", "lSubject", "cSubject"):
        if item.get(key):
            return str(item[key])
    return str(item)[:200]


# دسته‌بندی سبک بر اساس کلیدواژه‌ی عنوان -- چون تأثیر «افزایش سرمایه» و
# «گزارش فعالیت ماهانه» روی قیمت کاملاً متفاوته و اگه با هم قاطی بشن،
# میانگین تأثیر بی‌معنی می‌شه.
_CODAL_CATEGORIES = [
    ("افزایش سرمایه", "افزایش سرمایه"),
    ("کاهش سرمایه", "کاهش سرمایه"),
    ("مجمع", "مجمع"),
    ("پیش بینی سود", "پیش‌بینی سود"),
    ("پیش‌بینی سود", "پیش‌بینی سود"),
    ("صورت", "صورت‌های مالی"),
    ("فعالیت ماه", "گزارش فعالیت ماهانه"),
    ("قرارداد", "قرارداد/رویداد مهم"),
    ("توقف", "توقف نماد"),
    ("بازگشایی", "بازگشایی نماد"),
    ("افشای اطلاعات", "افشای اطلاعات بااهمیت"),
]


def _categorize(title):
    for keyword, label in _CODAL_CATEGORIES:
        if keyword in title:
            return label
    return "سایر"


def _extract_id(item):
    for key in ("tracingNo", "TracingNo", "id", "Id", "insMsgID", "msgID"):
        if item.get(key) is not None:
            return str(item[key])
    return None


def check_daily_news(db_path=None, ins_code=None):
    """هر دو منبع رو می‌گیره، فقط موارد جدید (که قبلاً دیده نشده) رو
    برمی‌گردونه -- چون این هر ۵ دقیقه صدا زده می‌شه و نباید هر بار همون
    خبر قدیمی رو دوباره اعلام کنه."""
    db_path = db_path or config.DATABASE_NAME
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    _ensure_table(cur)

    new_items = []
    news_price = _current_stock_price(cur)

    codal_items = fetch_codal_notifications(ins_code)
    for item in codal_items:
        item_id = _extract_id(item) or _extract_title(item)
        cur.execute("SELECT 1 FROM daily_news WHERE source='codal' AND item_id=?", (item_id,))
        if cur.fetchone():
            continue
        title = _extract_title(item)
        category = _categorize(title)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO daily_news(time, source, item_id, title, raw, price_at_news, category) VALUES (?,?,?,?,?,?,?)",
            (now, "codal", item_id, title, str(item)[:1000], news_price, category),
        )
        new_items.append({"source": "کدال", "title": title, "category": category})

    msg_items = fetch_supervisor_messages(ins_code)
    for item in msg_items:
        item_id = _extract_id(item) or _extract_title(item)
        cur.execute("SELECT 1 FROM daily_news WHERE source='supervisor' AND item_id=?", (item_id,))
        if cur.fetchone():
            continue
        title = _extract_title(item)
        category = _categorize(title)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO daily_news(time, source, item_id, title, raw, price_at_news, category) VALUES (?,?,?,?,?,?,?)",
            (now, "supervisor", item_id, title, str(item)[:1000], news_price, category),
        )
        new_items.append({"source": "ناظر بازار", "title": title, "category": category})

    conn.commit()
    conn.close()
    return new_items


if __name__ == "__main__":
    items = check_daily_news()
    if items:
        print(f"{len(items)} خبر جدید:")
        for it in items:
            print(f"  [{it['source']}] {it['title']}")
    else:
        print("خبر جدیدی نیست (یا داده‌ای دریافت نشد -- پیام‌های بالا رو چک کن).")