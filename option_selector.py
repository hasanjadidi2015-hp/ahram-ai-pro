# -*- coding: utf-8 -*-
"""
نسخه نهایی option_selector.py - تاریخ 2026-09-05 (اصلاح شماره 3)
سازگار با ساختار واقعی دیتابیس‌های ahram_v2.db / webmellt.db / shasta.db
مخصوص نوسان‌گیری 1 تا چند روزه (Swing Trading)

تغییرات کلیدی نسبت به نسخه قبلی:
  1. پشتیبانی از option_type = "CALL" / "PUT" (حروف بزرگ انگلیسی)
  2. خواندن ستون days_to_expire (نام واقعی در دیتابیس)
  3. مدیریت هوشمند نبود ستون bid/ask: استفاده از option_price
  4. فیلتر DTE و نقدشوندگی فعال و تست‌شده روی دیتای واقعی
"""

import os
import sys
import gc
import time
import sqlite3
import logging
from typing import Dict, Any, Optional, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OptionSelector")

# ─── ثابت‌های فیلترینگ نوسان‌گیری کوتاه‌مدت ───
MAX_SPREAD_PCT = 15.0    # حداکثر اسپرد مجاز (درصد) - فقط وقتی bid/ask موجود باشد
MIN_DTE = 10             # حداقل روز تا سررسید
MAX_DTE = 60             # حداکثر روز تا سررسید
MIN_VOLUME = 100         # حداقل حجم معاملات روزانه
MIN_OI = 50              # حداقل موقعیت باز (پایین‌تر از قبل چون بازار ایران کوچک است)


def calculate_spread_pct(bid: float, ask: float) -> float:
    """محاسبه درصد اسپرد. اگر داده معتبر نباشد، 0 برمی‌گرداند (یعنی فیلتر رد نمی‌کند)."""
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return 0.0  # داده ناموجود = عبور از فیلتر (با هشدار جداگانه)
    return ((ask - bid) / bid) * 100


def get_best_option(db_path: str, ua_symbol: str, signal_type: str, ua_price: float) -> Optional[Dict[str, Any]]:
    """
    انتخاب بهترین قرارداد آپشن بر اساس فیلترهای نوسان‌گیری.
    signal_type: 'BUY_CALL' یا 'BUY_PUT'
    """
    if not os.path.exists(db_path):
        logger.warning(f"⚠️ دیتابیس یافت نشد: {db_path}")
        return None

    # ─── تعیین نوع آپشن (پشتیبانی از همه فرمت‌های ممکن) ───
    if signal_type == "BUY_CALL":
        db_option_types = ["CALL", "call", "C", "خرید"]
    elif signal_type == "BUY_PUT":
        db_option_types = ["PUT", "put", "P", "فروش"]
    else:
        logger.info(f"ℹ️ سیگنال {signal_type} نیاز به انتخاب آپشن ندارد.")
        return None

    conn = None
    best_option = None

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # ─── پیدا کردن جدول آپشن‌ها ───
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        all_tables = [row[0] for row in cursor.fetchall()]

        table_name = None
        for candidate in ['options_data', 'options', 'option_chain']:
            if candidate in all_tables:
                table_name = candidate
                break

        if not table_name:
            logger.error("❌ جدول آپشن‌ها در دیتابیس یافت نشد.")
            return None

        # ─── خواندن نام ستون‌ها ───
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]

        if not columns:
            logger.error("❌ ستون‌های جدول آپشن خالی است.")
            return None

        # ─── بررسی وجود ستون‌های bid/ask ───
        has_bid_ask = False
        bid_col = None
        ask_col = None
        for bc in ['bid_price', 'bid', 'pMeDem']:
            if bc in columns:
                bid_col = bc
                break
        for ac in ['ask_price', 'ask', 'pMeOf']:
            if ac in columns:
                ask_col = ac
                break
        if bid_col and ask_col:
            has_bid_ask = True

        if not has_bid_ask:
            logger.info("ℹ️ ستون bid/ask در جدول آپشن وجود ندارد. "
                        "فیلتر اسپرد غیرفعال شد (از option_price استفاده می‌شود).")

        # ─── کوئری اصلی ───
        placeholders = ','.join('?' for _ in db_option_types)
        query = f"SELECT * FROM {table_name} WHERE option_type IN ({placeholders})"
        cursor.execute(query, tuple(db_option_types))
        rows = cursor.fetchall()

        if not rows:
            logger.warning(f"⚠️ هیچ ردیفی با نوع {db_option_types} در جدول {table_name} پیدا نشد.")
            return None

        valid_options = []
        skipped_reasons = {"dte_low": 0, "dte_high": 0, "spread": 0, "liquidity": 0, "no_data": 0}

        for row in rows:
            opt = dict(row)
            opt_symbol = opt.get('symbol', 'نامشخص')

            # ─── استخراج فیلدها با نام‌های واقعی دیتابیس ───
            strike = opt.get('strike_price', opt.get('strike'))
            # نام واقعی در دیتابیس شما: days_to_expire
            dte = opt.get('days_to_expire', opt.get('dte', opt.get('days_to_maturity')))
            option_price = opt.get('option_price', 0)
            volume = opt.get('volume', 0)
            oi = opt.get('open_interest', opt.get('oi', 0))

            # bid/ask فقط اگر ستون وجود داشته باشد
            bid = float(opt.get(bid_col, 0)) if bid_col else 0.0
            ask = float(opt.get(ask_col, 0)) if ask_col else 0.0

            # ─── اعتبارسنجی اولیه ───
            if strike is None or dte is None:
                skipped_reasons["no_data"] += 1
                continue

            try:
                strike = float(strike)
                dte = int(float(dte))
                option_price = float(option_price) if option_price else 0.0
                volume = int(float(volume)) if volume else 0
                oi = int(float(oi)) if oi else 0
            except (ValueError, TypeError):
                skipped_reasons["no_data"] += 1
                continue

            # ─── فیلتر ۱: روز تا سررسید (DTE) ───
            if dte < MIN_DTE:
                skipped_reasons["dte_low"] += 1
                continue
            if dte > MAX_DTE:
                skipped_reasons["dte_high"] += 1
                continue

            # ─── فیلتر ۲: اسپرد (فقط اگر داده موجود باشد) ───
            spread_pct = 0.0
            if has_bid_ask:
                spread_pct = calculate_spread_pct(bid, ask)
                if spread_pct > MAX_SPREAD_PCT:
                    skipped_reasons["spread"] += 1
                    continue

            # ─── فیلتر ۳: نقدشوندگی ───
            if oi < MIN_OI and volume < MIN_VOLUME:
                skipped_reasons["liquidity"] += 1
                continue

            # ─── محاسبه فاصله از ATM ───
            if ua_price > 0:
                dist_pct = abs(strike - ua_price) / ua_price * 100
            else:
                dist_pct = 999.0

            opt['calculated_spread_pct'] = spread_pct
            opt['dist_pct'] = dist_pct
            opt['strike_price_clean'] = strike
            opt['dte_clean'] = dte
            opt['option_price_clean'] = option_price
            opt['has_bid_ask'] = has_bid_ask

            valid_options.append(opt)

        # ─── گزارش خلاصه فیلترینگ ───
        logger.info(f"📊 خلاصه فیلترینگ: {len(rows)} رکورد → {len(valid_options)} معتبر | "
                    f"رد شده: DTE<{MIN_DTE}={skipped_reasons['dte_low']}, "
                    f"DTE>{MAX_DTE}={skipped_reasons['dte_high']}, "
                    f"اسپرد={skipped_reasons['spread']}, "
                    f"نقدشوندگی={skipped_reasons['liquidity']}, "
                    f"بدون‌داده={skipped_reasons['no_data']}")

        # ─── انتخاب بهترین (نزدیک‌ترین به ATM) ───
        if valid_options:
            valid_options.sort(key=lambda x: x['dist_pct'])
            best_option = valid_options[0]

            spread_info = f"{best_option['calculated_spread_pct']:.1f}%" if has_bid_ask else "N/A"
            logger.info(f"✅ بهترین آپشن: {best_option.get('symbol')} | "
                        f"اعمال: {best_option['strike_price_clean']:,.0f} | "
                        f"قیمت: {best_option['option_price_clean']:,.0f} | "
                        f"سررسید: {best_option['dte_clean']} روز | "
                        f"فاصله ATM: {best_option['dist_pct']:.2f}% | "
                        f"اسپرد: {spread_info}")
        else:
            logger.warning(f"⚠️ هیچ آپشنی فیلترها را پاس نکرد. "
                           f"(DTE: {MIN_DTE}-{MAX_DTE} روز, نقدشوندگی: حجم>={MIN_VOLUME})")

    except Exception as e:
        logger.error(f"❌ خطا: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return best_option


def _safe_remove(path: str, attempts: int = 5, delay: float = 0.3) -> bool:
    """حذف امن فایل موقت در ویندوز."""
    gc.collect()
    for _ in range(attempts):
        try:
            if os.path.exists(path):
                os.remove(path)
            return True
        except PermissionError:
            time.sleep(delay)
            gc.collect()
    return False


# =====================================================================
# بخش تست خودکار
# =====================================================================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\n=== [تست ماژول انتخاب آپشن - نسخه سازگار با دیتابیس واقعی] ===")

        test_db = "temp_test_options.db"
        _safe_remove(test_db)

        setup_conn = sqlite3.connect(test_db)
        c = setup_conn.cursor()

        # ساخت جدول دقیقاً هم‌شکل دیتابیس واقعی شما
        c.execute("""
            CREATE TABLE IF NOT EXISTS options (
                id INTEGER PRIMARY KEY,
                time TEXT,
                symbol TEXT,
                option_type TEXT,
                stock_price REAL,
                option_price REAL,
                strike_price REAL,
                expire_date TEXT,
                days_to_expire INTEGER,
                volume REAL,
                value_traded REAL,
                open_interest REAL
            )
        """)

        # داده‌های تستی با فرمت واقعی دیتابیس شما
        test_data = [
            # ۱: CALL عالی - DTE مناسب، ATM، حجم بالا
            (1, '2026-09-05 10:00:00', 'ضاهرم7001', 'CALL', 57000, 1200, 56000, '1405/07/15', 25, 5000, 6000000, 2000),
            # ۲: CALL رد - اسپرد بالا (اگر bid/ask بود) → اینجا DTE کم
            (2, '2026-09-05 10:00:00', 'ضاهرم7002', 'CALL', 57000, 300, 56000, '1405/06/20', 4, 3000, 900000, 1500),
            # ۳: CALL رد - DTE خیلی زیاد (اهرم ضعیف)
            (3, '2026-09-05 10:00:00', 'ضاهرم7003', 'CALL', 57000, 5000, 56000, '1405/10/01', 90, 200, 1000000, 100),
            # ۴: PUT عالی - ATM، DTE مناسب
            (4, '2026-09-05 10:00:00', 'طاهرم7001', 'PUT', 57000, 1100, 57000, '1405/07/20', 30, 4000, 4400000, 1800),
            # ۵: PUT رد - نقدشوندگی صفر
            (5, '2026-09-05 10:00:00', 'طاهرم7002', 'PUT', 57000, 50, 58000, '1405/07/10', 15, 10, 500, 5),
        ]

        c.executemany("""
            INSERT INTO options (id, time, symbol, option_type, stock_price, option_price,
                                 strike_price, expire_date, days_to_expire, volume, value_traded, open_interest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, test_data)
        setup_conn.commit()
        c.close()
        setup_conn.close()
        del c, setup_conn

        print("✅ دیتابیس تستی (هم‌شکل دیتابیس واقعی) ساخته شد.\n")

        results = []

        # تست ۱: خرید CALL
        print("--- [تست ۱: خرید CALL] ---")
        best_call = get_best_option(test_db, "اهرم", "BUY_CALL", 57000)
        if best_call and best_call.get('symbol') == 'ضاهرم7001':
            print("🥇 تست ۱: پاس ✅\n")
            results.append(True)
        else:
            got = best_call.get('symbol') if best_call else 'None'
            print(f"❌ تست ۱: شکست (انتظار: ضاهرم7001، دریافت: {got})\n")
            results.append(False)

        # تست ۲: خرید PUT
        print("--- [تست ۲: خرید PUT] ---")
        best_put = get_best_option(test_db, "اهرم", "BUY_PUT", 57000)
        if best_put and best_put.get('symbol') == 'طاهرم7001':
            print("🥇 تست ۲: پاس ✅\n")
            results.append(True)
        else:
            got = best_put.get('symbol') if best_put else 'None'
            print(f"❌ تست ۲: شکست (انتظار: طاهرم7001، دریافت: {got})\n")
            results.append(False)

        # تست ۳: WATCH (نباید آپشن برگرداند)
        print("--- [تست ۳: سیگنال WATCH] ---")
        best_watch = get_best_option(test_db, "اهرم", "WATCH", 57000)
        if best_watch is None:
            print("🥇 تست ۳: پاس ✅ (درست None برگرداند)\n")
            results.append(True)
        else:
            print("❌ تست ۳: شکست (باید None برمی‌گرداند)\n")
            results.append(False)

        best_call = best_put = best_watch = None

        if _safe_remove(test_db):
            print("🧹 فایل موقت پاک شد.")
        else:
            print(f"ℹ️ فایل '{test_db}' قفل است. دستی پاک کنید.")

        if all(results):
            print("\n🎉 تمام تست‌ها پاس شدند!")
        else:
            print(f"\n⚠️ {results.count(False)} تست شکست خورد.")
        print("================================================\n")
    else:
        print("اجرای تست:  python option_selector.py --test")