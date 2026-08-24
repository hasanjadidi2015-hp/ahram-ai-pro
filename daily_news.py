# -*- coding: utf-8 -*-
"""
اخبار رسمی روزانه:
- اطلاعیه‌های کدال مرتبط با نماد از مسیر TSETMC
- پیام‌های ناظر بازار مرتبط با نماد

نکته مهم:
در اولین اجرا، خبرهای قبلی فقط به‌عنوان Baseline در دیتابیس ذخیره می‌شوند
و هیچ نوتیفیکیشنی ارسال نمی‌شود. از اجرای بعد، فقط موارد واقعاً جدید
برگردانده می‌شوند تا ربات برای خبرهای قدیمی هشدار نفرستد.
"""

import json
import sqlite3
import time
from datetime import datetime

import requests

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
    """دریافت امن JSON از TSETMC."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=(4, 10),
            )
        except requests.exceptions.RequestException as e:
            print(f"[NEWS] CONNECTION ERROR ({attempt}/{max_retries}): {e}")
            time.sleep(1)
            continue

        if response.status_code != 200:
            print(
                f"[NEWS] SERVER ERROR ({attempt}/{max_retries}): "
                f"HTTP {response.status_code}"
            )
            time.sleep(1)
            continue

        if not response.text or not response.text.strip():
            print(f"[NEWS] EMPTY RESPONSE ({attempt}/{max_retries})")
            time.sleep(1)
            continue

        try:
            return response.json()
        except ValueError:
            print(f"[NEWS] INVALID JSON: {response.text[:300]}")
            return None

    return None


def fetch_codal_notifications(ins_code=None, top=10):
    """دریافت اطلاعیه‌های کدال مرتبط با نماد از API TSETMC."""
    ins_code = ins_code or config.INS_CODE

    url = (
        "https://cdn.tsetmc.com/api/"
        f"Codal/GetPreparedDataByInsCode/{top}/{ins_code}"
    )

    data = _get_json(url)

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        items = (
            data.get("codalPreparedData")
            or data.get("codal")
            or data.get("data")
            or []
        )

        if isinstance(items, list):
            return items

    print("[NEWS] CODAL RESPONSE SHAPE UNKNOWN:", str(data)[:500])
    return []


def fetch_supervisor_messages(ins_code=None):
    """دریافت پیام‌های ناظر بازار مرتبط با نماد."""
    ins_code = ins_code or config.INS_CODE

    url = (
        "https://cdn.tsetmc.com/api/"
        f"Msg/GetMsgByInsCode/{ins_code}"
    )

    data = _get_json(url)

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        items = (
            data.get("insMsg")
            or data.get("msg")
            or data.get("data")
            or []
        )

        if isinstance(items, list):
            return items

    print("[NEWS] SUPERVISOR RESPONSE SHAPE UNKNOWN:", str(data)[:500])
    return []


def _ensure_table(cur):
    """ساخت/ارتقای جدول خبرها و تنظیمات اولیه."""

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

    # سازگاری با دیتابیس‌های قبلی
    cur.execute("PRAGMA table_info(daily_news)")
    existing_columns = {row[1] for row in cur.fetchall()}

    needed_columns = [
        ("price_at_news", "REAL"),
        ("outcome_pct_1d", "REAL"),
        ("outcome_pct_5d", "REAL"),
        ("outcome_pct_20d", "REAL"),
        ("fully_evaluated", "INTEGER DEFAULT 0"),
        ("category", "TEXT"),
    ]

    for column_name, column_type in needed_columns:
        if column_name not in existing_columns:
            try:
                cur.execute(
                    f"ALTER TABLE daily_news "
                    f"ADD COLUMN {column_name} {column_type}"
                )
            except Exception as e:
                print(f"[NEWS] COLUMN MIGRATION ERROR ({column_name}): {e}")

    # جلوگیری از ذخیره رکورد تکراری
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_news_unique
        ON daily_news(source, item_id)
    """)

    # تنظیمات اختصاصی هر دیتابیس نماد
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            updated_at TEXT
        )
    """)


def _setting_get(cur, key, default=None):
    cur.execute(
        "SELECT setting_value FROM news_settings WHERE setting_key=?",
        (key,),
    )
    row = cur.fetchone()
    return row[0] if row else default


def _setting_set(cur, key, value):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO news_settings(setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key)
        DO UPDATE SET
            setting_value=excluded.setting_value,
            updated_at=excluded.updated_at
    """, (key, str(value), now))


def _current_stock_price(cur):
    """آخرین قیمت ذخیره‌شده دارایی پایه."""
    cur.execute("""
        SELECT last_price
        FROM prices
        WHERE last_price IS NOT NULL
          AND last_price > 0
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cur.fetchone()

    try:
        return float(row[0]) if row and row[0] else None
    except Exception:
        return None


def _extract_title(item):
    """
    استخراج عنوان از پاسخ‌های متفاوت TSETMC.

    برای پیام ناظر واقعی، tseTitle مهم‌ترین فیلد است.
    """
    if not isinstance(item, dict):
        return str(item)[:300]

    for key in (
        "tseTitle",
        "title",
        "lTitle",
        "Title",
        "subject",
        "lSubject",
        "cSubject",
    ):
        value = item.get(key)

        if value:
            return str(value).strip()

    description = (
        item.get("tseDesc")
        or item.get("description")
        or item.get("desc")
    )

    if description:
        return str(description).strip()[:300]

    return str(item)[:300]


def _extract_id(item):
    """
    استخراج شناسه یکتای رسمی خبر.

    برای پیام ناظر TSETMC، tseMsgIdn فیلد واقعی شناسه است.
    """
    if not isinstance(item, dict):
        return None

    for key in (
        "tseMsgIdn",
        "tracingNo",
        "TracingNo",
        "id",
        "Id",
        "insMsgID",
        "msgID",
        "letterSerial",
        "LetterSerial",
    ):
        value = item.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    return None


_CATEGORIES = [
    ("توقف", "توقف نماد"),
    ("بازگشایی", "بازگشایی نماد"),
    ("عدم تأیید", "عدم تأیید معاملات"),
    ("عدم تاييد", "عدم تأیید معاملات"),
    ("تسویه", "تسویه اختیار معامله"),
    ("تسويه", "تسویه اختیار معامله"),
    ("افزایش سرمایه", "افزایش سرمایه"),
    ("افزايش سرمايه", "افزایش سرمایه"),
    ("کاهش سرمایه", "کاهش سرمایه"),
    ("مجمع", "مجمع"),
    ("افشای اطلاعات", "افشای اطلاعات بااهمیت"),
    ("افشاي اطلاعات", "افشای اطلاعات بااهمیت"),
    ("گزارش فعالیت", "گزارش فعالیت"),
    ("گزارش فعاليت", "گزارش فعالیت"),
    ("صورت مالی", "صورت‌های مالی"),
    ("صورت مالي", "صورت‌های مالی"),
    ("قرارداد اختیار", "اطلاعیه اختیار معامله"),
    ("قرارداد اختيار", "اطلاعیه اختیار معامله"),
    ("آغاز دوره معاملاتی", "شروع معامله اختیار"),
    ("آغاز دوره معاملاتي", "شروع معامله اختیار"),
]


def _categorize(title):
    """دسته‌بندی ساده و قابل‌فهم خبر بر پایه عنوان."""
    normalized_title = (title or "").strip().lower()

    for keyword, category in _CATEGORIES:
        if keyword.lower() in normalized_title:
            return category

    return "سایر"


def _serialize_raw(item):
    """ذخیره امن پاسخ خام برای بررسی و دیباگ بعدی."""
    try:
        return json.dumps(
            item,
            ensure_ascii=False,
            default=str,
        )[:4000]
    except Exception:
        return str(item)[:4000]


def _save_item(
    cur,
    source,
    item,
    news_price,
):
    """
    ذخیره یک آیتم در دیتابیس.

    خروجی:
      (is_new, result_dictionary)
    """
    title = _extract_title(item)
    item_id = _extract_id(item)

    # اگر API شناسه رسمی نداشت، یک کلید fallback می‌سازیم
    if not item_id:
        item_id = f"title:{title[:250]}"

    category = _categorize(title)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        "SELECT 1 FROM daily_news WHERE source=? AND item_id=?",
        (source, item_id),
    )

    if cur.fetchone():
        return False, None

    cur.execute("""
        INSERT OR IGNORE INTO daily_news (
            time,
            source,
            item_id,
            title,
            raw,
            price_at_news,
            category
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        now,
        source,
        item_id,
        title,
        _serialize_raw(item),
        news_price,
        category,
    ))

    return True, {
        "source": "کدال" if source == "codal" else "ناظر بازار",
        "title": title,
        "category": category,
        "item_id": item_id,
        "time": now,
    }


def check_daily_news(
    db_path=None,
    ins_code=None,
    top=10,
):
    """
    بررسی خبرهای رسمی و پیام‌های ناظر.

    رفتار اجرای اول:
      - اطلاعات قبلی فقط ذخیره می‌شوند.
      - هیچ موردی به‌عنوان خبر تازه برگردانده نمی‌شود.
      - بنابراین هیچ نوتیفیکیشن تاریخی ارسال نخواهد شد.

    رفتار اجرای بعدی:
      - فقط مواردی که قبلاً در دیتابیس نبوده‌اند برگردانده می‌شوند.
    """
    db_path = db_path or config.DATABASE_NAME
    ins_code = ins_code or config.INS_CODE

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        _ensure_table(cur)
    except Exception as e:
        print("[NEWS] DATABASE INIT ERROR:", e)
        return []

    first_sync_done = _setting_get(
        cur,
        "daily_news_initial_sync_done",
        "0",
    ) == "1"

    news_price = _current_stock_price(cur)

    codal_items = fetch_codal_notifications(
        ins_code=ins_code,
        top=top,
    )

    supervisor_items = fetch_supervisor_messages(
        ins_code=ins_code,
    )

    inserted_items = []

    for item in codal_items:
        is_new, result = _save_item(
            cur,
            source="codal",
            item=item,
            news_price=news_price,
        )

        if is_new and result:
            inserted_items.append(result)

    for item in supervisor_items:
        is_new, result = _save_item(
            cur,
            source="supervisor",
            item=item,
            news_price=news_price,
        )

        if is_new and result:
            inserted_items.append(result)

    # اولین همگام‌سازی: ذخیره اطلاعات قدیمی، بدون هشدار
    if not first_sync_done:
        _setting_set(
            cur,
            "daily_news_initial_sync_done",
            "1",
        )

        conn.commit()
        conn.close()

        print(
            "[NEWS] INITIAL BASELINE COMPLETED: "
            f"{len(inserted_items)} مورد قدیمی ذخیره شد؛ "
            "هیچ نوتیفیکیشنی ارسال نمی‌شود."
        )

        return []

    conn.commit()
    conn.close()

    return inserted_items


if __name__ == "__main__":
    items = check_daily_news()

    if items:
        print(f"{len(items)} خبر جدید:")

        for item in items:
            print(
                f"  [{item['source']} | "
                f"{item['category']}] "
                f"{item['title']}"
            )
    else:
        print("خبر جدیدی نیست یا همگام‌سازی اولیه انجام شد.")