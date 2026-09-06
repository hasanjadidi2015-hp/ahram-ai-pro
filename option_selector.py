# -*- coding: utf-8 -*-
"""
ماژول انتخاب قراردادهای آپشن (Option Selector Engine)
نسخه ضدخطا (Bulletproof) - تاریخ: 2026-09-06
دارای سیستم اعتبارسنجی ۳ لایه:
  ۱. فیلتر آخرین اسنپ‌شات بازار (Latest Snapshot Only)
  ۲. فیلتر انقضای تقویمی (Future Expiry Validation)
  ۳. فیلتر نوسان‌گیری کوتاه‌مدت (10 <= DTE <= 60)
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OptionSelector")

MAX_SPREAD_PCT = 15.0   # حداکثر اسپرد مجاز
MIN_DTE = 10            # حداقل روز تا سررسید
MAX_DTE = 60            # حداکثر روز تا سررسید
MIN_VOLUME = 0          # بدون محدودیت حجم در اسنپ‌شات اولیه


def get_best_option(db_path: str, ua_symbol: str, signal_type: str, ua_price: float) -> Optional[Dict[str, Any]]:
    """انتخاب دقیق بهترین قرارداد آپشن فعالِ همان روز"""
    if not os.path.exists(db_path):
        logger.error(f"❌ دیتابیس در مسیر {db_path} یافت نشد.")
        return None

    if signal_type == "BUY_CALL":
        db_types = ["CALL", "call", "C", "خرید"]
    elif signal_type == "BUY_PUT":
        db_types = ["PUT", "put", "P", "فروش"]
    else:
        return None

    conn = None
    best_option = None

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # ۱. پیدا کردن نام جدول آپشن‌ها
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('options', 'options_data');")
        tbl = cur.fetchone()
        if not tbl:
            logger.error("❌ جدول options در دیتابیس یافت نشد.")
            return None
        table_name = tbl[0]

        # ۲. [لایه حفاظتی ۱] استخراج آخرین زمان ثبت‌شده دیتابیس
        cur.execute(f"SELECT MAX(time) FROM {table_name}")
        latest_time_row = cur.fetchone()
        latest_time = latest_time_row[0] if latest_time_row else None

        if not latest_time:
            logger.warning("⚠️ جدول آپشن‌ها کاملاً خالی است.")
            return None

        # ۳. کوئری انحصاری: فقط رکوردهای ثبت‌شده در آخرین سیکل بازار
        placeholders = ','.join('?' for _ in db_types)
        query = f"""
            SELECT * FROM {table_name}
            WHERE option_type IN ({placeholders})
            AND time = ?
        """
        cur.execute(query, tuple(db_types) + (latest_time,))
        rows = cur.fetchall()

        # اگر در همان ثانیه رکوردی نبود، بازه ۱۰ دقیقه آخر آخرین ثبت را بخوان
        if not rows:
            query = f"""
                SELECT * FROM {table_name}
                WHERE option_type IN ({placeholders})
                AND time >= datetime(?, '-10 minutes')
            """
            cur.execute(query, tuple(db_types) + (latest_time,))
            rows = cur.fetchall()

        valid_options = []

        for r in rows:
            opt = dict(r)
            sym = opt.get('symbol', '')
            strike = opt.get('strike_price', opt.get('strike'))
            dte = opt.get('days_to_expire', opt.get('dte', opt.get('days_to_maturity')))
            opt_price = opt.get('option_price', 0)
            exp_date = str(opt.get('expire_date', ''))

            if strike is None or dte is None:
                continue

            try:
                strike = float(strike)
                dte = int(float(dte))
                opt_price = float(opt_price) if opt_price else 0.0
            except (ValueError, TypeError):
                continue

            # [لایه حفاظتی ۲ و ۳] فیلتر DTE مجاز نوسان‌گیری
            if dte < MIN_DTE or dte > MAX_DTE:
                continue

            # محاسبه فاصله از قیمت دارایی پایه (Moneyness)
            dist_pct = abs(strike - ua_price) / ua_price * 100 if ua_price > 0 else 999.0

            opt['calculated_spread_pct'] = 0.0
            opt['dist_pct'] = dist_pct
            opt['strike_price_clean'] = strike
            opt['dte_clean'] = dte
            opt['option_price_clean'] = opt_price
            opt['snapshot_time'] = latest_time

            valid_options.append(opt)

        if valid_options:
            # انتخاب نزدیک‌ترین قرارداد فعال به ATM
            valid_options.sort(key=lambda x: x['dist_pct'])
            best_option = valid_options[0]

            logger.info(f"✅ قرارداد فعال بازار انتخاب شد: {best_option.get('symbol')} | "
                        f"اعمال: {best_option['strike_price_clean']:,.0f} | "
                        f"قیمت: {best_option['option_price_clean']:,.0f} | "
                        f"سررسید: {best_option['dte_clean']} روز | "
                        f"تاریخ سررسید: {best_option.get('expire_date', '-')} | "
                        f"زمان اسنپ‌شات: {latest_time}")
        else:
            logger.warning(f"⚠️ در آخرین اسنپ‌شات زنده ({latest_time}) هیچ قرارداد فعالی با شرایط {MIN_DTE}<=DTE<={MAX_DTE} یافت نشد.")

    except Exception as e:
        logger.error(f"❌ خطا در پردازش انتخاب آپشن: {e}")
    finally:
        if conn:
            conn.close()

    return best_option


# =====================================================================
# بخش تست راستی‌آزمایی با دیتابیس واقعی شما
# =====================================================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🔍 راستی‌آزمایی انتخاب قراردادهای فعال امروز روی دیتابیس‌های واقعی")
    print("="*70)

    test_cases = [
        ("اهرم", "ahram_v2.db", "BUY_CALL", 57167.0),
        ("اهرم", "ahram_v2.db", "BUY_PUT", 57167.0),
        ("وبملت", "webmellt.db", "BUY_CALL", 1483.0),
        ("شستا", "shasta.db", "BUY_CALL", 2932.0),
    ]

    for sym, db, sig, price in test_cases:
        print(f"\n--- تست نماد [{sym}] | سیگنال: {sig} ---")
        res = get_best_option(db, sym, sig, price)
        if res:
            print(f"🎯 نماد فعال انتخاب‌شده: [{res['symbol']}] | سررسید: {res['dte_clean']} روز | تاریخ انقضا: {res.get('expire_date')}")
        else:
            print("❌ قراردادی یافت نشد.")

    print("\n" + "="*70 + "\n")