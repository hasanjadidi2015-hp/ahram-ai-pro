# -*- coding: utf-8 -*-
"""
اخبار رسمی روزانه:
- اطلاعیه‌های کدال از TSETMC
- پیام‌های ناظر بازار از TSETMC

قوانین ایمنی:
1) خبرهای قدیمی ذخیره می‌شوند، اما اعلان نمی‌گیرند.
2) فقط خبرهای حداکثر MAX_NEWS_AGE_DAYS روز اخیر مجاز به اعلان هستند.
3) خبر بدون تاریخ معتبر فقط ذخیره می‌شود و اعلان ندارد.
4) در هر سیکل حداکثر MAX_ALERTS_PER_CYCLE اعلان خبری برگردانده می‌شود.
5) اطلاعیه‌های روتین چرخه‌ی عمر قرارداد آپشن/آتی (شروع/پایان دوره، تسویه)
   حتی اگه تازه هم باشن، اعلان نمی‌گیرن -- فقط ذخیره می‌شن -- چون خبر
   واقعی نیستن، هر ماه برای هر سری قرارداد پیش میان.
"""

import json
import sqlite3
import time
from datetime import datetime, date

import requests

import config


MAX_NEWS_AGE_DAYS = 1
MAX_ALERTS_PER_CYCLE = 2

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
            print("[NEWS] INVALID JSON:", response.text[:300])
            return None

    return None


def fetch_codal_notifications(ins_code=None, top=10):
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
        # نکته: کلید واقعی پاسخ TSETMC "preparedData"ست (تأیید شده روی
        # داده‌ی زنده) -- بقیه‌ی کلیدها fallback احتیاطی‌ان.
        items = (
            data.get("preparedData")
            or data.get("codalPreparedData")
            or data.get("codal")
            or data.get("data")
            or []
        )

        if isinstance(items, list):
            return items

    print("[NEWS] CODAL RESPONSE SHAPE UNKNOWN:", str(data)[:500])
    return []


def fetch_supervisor_messages(ins_code=None):
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            source TEXT,
            item_id TEXT,
            title TEXT,
            raw TEXT,
            event_date TEXT,
            price_at_news REAL,
            outcome_pct_1d REAL,
            outcome_pct_5d REAL,
            outcome_pct_20d REAL,
            fully_evaluated INTEGER DEFAULT 0,
            category TEXT
        )
    """)

    cur.execute("PRAGMA table_info(daily_news)")
    existing_columns = {row[1] for row in cur.fetchall()}

    needed_columns = [
        ("event_date", "TEXT"),
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
                print(f"[NEWS] COLUMN MIGRATION ERROR {column_name}: {e}")

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_news_unique
        ON daily_news(source, item_id)
    """)

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

    for key in ("tseDesc", "description", "desc"):
        value = item.get(key)

        if value:
            return str(value).strip()[:300]

    return str(item)[:300]


def _extract_id(item):
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


def _extract_event_date(item):
    """
    تاریخ خبر را برمی‌گرداند.

    فیلدهای رایج TSETMC:
      پیام ناظر بازار : dEven = 20260824
      اطلاعیه کدال     : publishDateTime_DEven = 20260727

    خروجی:
      YYYY-MM-DD
    یا:
      None
    """
    if not isinstance(item, dict):
        return None

    possible_fields = (
        "dEven",
        "publishDateTime_DEven",
        "date",
        "publishDate",
        "publish_date",
        "dateTime",
        "sendDate",
        "publishDateTime_Gregorian",
        "sentDateTime_Gregorian",
    )

    for key in possible_fields:
        value = item.get(key)

        if value is None:
            continue

        digits = "".join(char for char in str(value) if char.isdigit())

        # فرمت رایج TSETMC: YYYYMMDD (اول رشته، چه خودش عدد خام باشه چه
        # بخش اول یه datetime ایزو مثل 2026-07-27T08:18:26)
        if len(digits) >= 8:
            digits = digits[:8]

            try:
                parsed = datetime.strptime(
                    digits,
                    "%Y%m%d",
                ).date()

                return parsed.isoformat()

            except ValueError:
                continue

    return None


def _is_recent_event(event_date_text):
    """
    فقط خبرهای امروز و حداکثر MAX_NEWS_AGE_DAYS روز اخیر اجازه اعلان دارند.

    خبر بدون تاریخ معتبر:
    ذخیره می‌شود، اما اعلان ندارد.
    """
    if not event_date_text:
        return False

    try:
        event_day = datetime.strptime(
            event_date_text,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return False

    age_days = (date.today() - event_day).days

    return 0 <= age_days <= MAX_NEWS_AGE_DAYS


_CATEGORIES = [
    ("توقف", "توقف نماد"),
    ("بازگشایی", "بازگشایی نماد"),
    ("عدم تأیید", "عدم تأیید معاملات"),
    ("عدم تاييد", "عدم تأیید معاملات"),
    ("تسویه", "تسویه اختیار معامله"),
    ("تسويه", "تسویه اختیار معامله"),
    ("افزایش سرمایه", "افزایش سرمایه"),
    ("افزايش سرمايه", "افزایش سرمایه"),
    ("مجمع", "مجمع"),
    ("افشای اطلاعات", "افشای اطلاعات بااهمیت"),
    ("افشاي اطلاعات", "افشای اطلاعات بااهمیت"),
    ("گزارش فعالیت", "گزارش فعالیت"),
    ("گزارش فعاليت", "گزارش فعالیت"),
    ("صورت مالی", "صورت‌های مالی"),
    ("صورت مالي", "صورت‌های مالی"),
    ("قرارداد اختيار", "اطلاعیه اختیار معامله"),
    ("قرارداد اختیار", "اطلاعیه اختیار معامله"),
    ("آغاز دوره معاملاتي", "شروع معامله اختیار"),
    ("آغاز دوره معاملاتی", "شروع معامله اختیار"),
]


def _categorize(title):
    normalized_title = (title or "").strip().lower()

    for keyword, category in _CATEGORIES:
        if keyword.lower() in normalized_title:
            return category

    return "سایر"


# پیام‌های ناظر بازار پر از اطلاعیه‌های روتین چرخه‌ی عمر قرارداد
# آپشن/آتی‌ان (شروع/پایان دوره، تسویه) که هر ماه برای هر سری قرارداد جدید
# پیش میان -- حتی اگه امروز هم منتشر شده باشن، خبر واقعی نیستن، فقط نویز.
# اینا رو ثبت می‌کنیم (برای تاریخچه) ولی نوتیفای نمی‌کنیم.
_ROUTINE_KEYWORDS = [
    "آغاز دوره معاملاتي", "آغاز دوره معاملاتی",
    "پايان دوره معاملاتي", "پایان دوره معاملاتی",
    "تسويه نهايي", "تسویه نهایی",
    "تسويه نقدي", "تسویه نقدی",
    "تسويه فيزيكي", "تسویه فیزیکی",
    "اطلاعيه درخصوص قرارداد اختيار معامله", "اطلاعیه درخصوص قرارداد اختیار معامله",
]


def _is_routine(title):
    return any(kw in (title or "") for kw in _ROUTINE_KEYWORDS)


def _serialize_raw(item):
    try:
        return json.dumps(
            item,
            ensure_ascii=False,
            default=str,
        )[:4000]
    except Exception:
        return str(item)[:4000]


def _save_item(cur, source, item, news_price):
    """آیتم را ذخیره می‌کند و اطلاعات آن را برمی‌گرداند."""
    title = _extract_title(item)
    item_id = _extract_id(item)
    event_date = _extract_event_date(item)

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
            event_date,
            price_at_news,
            category
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now,
        source,
        item_id,
        title,
        _serialize_raw(item),
        event_date,
        news_price,
        category,
    ))

    result = {
        "source": "کدال" if source == "codal" else "ناظر بازار",
        "title": title,
        "category": category,
        "item_id": item_id,
        "event_date": event_date,
        "time": now,
    }

    return True, result


def check_daily_news(db_path=None, ins_code=None, top=10):
    """
    خبرها را ذخیره می‌کند؛ فقط موارد جدید، تازه، و غیرروتین را برای اعلان
    برمی‌گرداند.
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

    initial_sync_done = (
        _setting_get(
            cur,
            "daily_news_initial_sync_done",
            "0",
        ) == "1"
    )

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

    # اولین اجرا: همه‌چیز ذخیره شود، اما هشدار نده
    if not initial_sync_done:
        _setting_set(
            cur,
            "daily_news_initial_sync_done",
            "1",
        )

        conn.commit()
        conn.close()

        print(
            "[NEWS] INITIAL BASELINE COMPLETED: "
            f"{len(inserted_items)} مورد ذخیره شد؛ "
            "هیچ نوتیفیکیشنی ارسال نمی‌شود."
        )

        return []

    conn.commit()
    conn.close()

    # فقط خبرهای تازه و غیرروتین به چرخه اصلی برگردند.
    alertable_items = [
        item for item in inserted_items
        if _is_recent_event(item.get("event_date")) and not _is_routine(item.get("title"))
    ]

    routine_count = sum(
        1 for item in inserted_items
        if _is_recent_event(item.get("event_date")) and _is_routine(item.get("title"))
    )
    if routine_count:
        print(f"[NEWS] {routine_count} خبر تازه ولی روتین بود (فقط ذخیره شد، اعلان نداد).")

    # سقف اعلان برای جلوگیری از کندشدن ربات
    if len(alertable_items) > MAX_ALERTS_PER_CYCLE:
        print(
            f"[NEWS] {len(alertable_items)} خبر تازه پیدا شد؛ "
            f"فقط {MAX_ALERTS_PER_CYCLE} مورد اول اعلان می‌گیرند."
        )

    old_count = len(inserted_items) - len(alertable_items) - routine_count

    if old_count > 0:
        print(
            f"[NEWS] {old_count} مورد قدیمی/بدون تاریخ فقط ذخیره شد؛ "
            "اعلان ندارد."
        )

    return alertable_items[:MAX_ALERTS_PER_CYCLE]


if __name__ == "__main__":
    items = check_daily_news()

    if items:
        print(f"{len(items)} خبر تازه و قابل‌اعلان:")

        for item in items:
            print(
                f"  [{item['source']} | "
                f"{item['event_date']} | "
                f"{item['category']}] "
                f"{item['title']}"
            )
    else:
        print("خبر تازه و قابل‌اعلان وجود ندارد.")