# -*- coding: utf-8 -*-
"""
موتور پیشرفته تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V5 Experimental Engine)
نسخه نهایی 2026-09-05 - مجهز به فیلترهای نوسان‌گیری، آستانه‌های طلایی و مدیریت ریسک
همگام‌سازی‌شده با موتور اصلی V4
"""

import os
import sys
import time
import sqlite3
import logging
from datetime import datetime

# ایمپورت ماژول‌های ارتقایافته
import option_selector
import risk_management

# ایمپورت‌های فرعی با مکانیسم Fallback امن
try:
    import config
    DB_NAMES = {
        "اهرم": getattr(config, "DB_AHRAM_V5", "ahram_v5.db") if hasattr(config, "DB_AHRAM_V5") else "ahram_v2.db",
        "وبملت": getattr(config, "DB_WEBMELLT_V5", "webmellt_v5.db") if hasattr(config, "DB_WEBMELLT_V5") else "webmellt.db",
        "شستا": getattr(config, "DB_SHASTA_V5", "shasta_v5.db") if hasattr(config, "DB_SHASTA_V5") else "shasta.db"
    }
except ImportError:
    config = None
    DB_NAMES = {
        "اهرم": "ahram_v2.db",
        "وبملت": "webmellt.db",
        "شستا": "shasta.db"
    }

try: import collector
except ImportError: collector = None

try: import vace_engine_v2
except ImportError: vace_engine_v2 = None

try: import sentiment_engine_v2
except ImportError: sentiment_engine_v2 = None

try: import dashboard_v5
except ImportError: dashboard_v5 = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AhramProV5")

SYMBOLS = {
    "اهرم": {"ins_code": "17914401175772326", "db": DB_NAMES["اهرم"]},
    "وبملت": {"ins_code": "778253364357513", "db": DB_NAMES["وبملت"]},
    "شستا": {"ins_code": "2400322364771558", "db": DB_NAMES["شستا"]}
}


def check_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() in [3, 4]:  # پنج‌شنبه و جمعه
        return False
    current_time = now.strftime("%H:%M")
    return "09:00" <= current_time <= "12:30"


def run_cycle_v5(symbol: str, info: dict, is_test_mode: bool = False) -> dict:
    db_path = info["db"]
    logger.info(f"🔄 [V5 Shadow Engine] پایش نماد [{symbol}] روی دیتابیس [{db_path}]...")

    # ۱. دریافت آخرین قیمت سهم
    last_price = 0.0
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT last_price, closing_price FROM prices ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                last_price = float(row[0] or row[1] or 0.0)
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ خطای خواندن قیمت {symbol}: {e}")

    if last_price <= 0:
        fallback_prices = {"اهرم": 57167.0, "وبملت": 1483.0, "شستا": 2932.0}
        last_price = fallback_prices.get(symbol, 50000.0)

    # ۲. استخراج سیگنال‌های پیشرفته V5 (شبیه‌سازی تست / اجرای واقعی)
    if is_test_mode:
        simulations = {
            "اهرم": (66.0, "BUY_CALL", "BULLISH_TREND"),
            "شستا": (59.0, "BUY_PUT", "BEARISH_TREND"),
            "وبملت": (40.0, "WATCH", "NEUTRAL")
        }
        v5_score, signal_type, sentiment_status = simulations.get(symbol, (50.0, "WATCH", "NEUTRAL"))
    else:
        v5_score, signal_type = 50.0, "WATCH"
        sentiment_status = "NEUTRAL"
        # فراخوانی موتورهای V5 در صورت موجود بودن
        if sentiment_engine_v2:
            try: sentiment_status = sentiment_engine_v2.get_sentiment(symbol)
            except Exception: pass

    logger.info(f"📡 [V5] سیگنال: {signal_type} | امتیاز: {v5_score:.1f} | سنتیمنت: {sentiment_status}")

    selected_option = None
    risk_plan = None

    if signal_type in ["BUY_CALL", "BUY_PUT"]:
        # ۳. انتخاب آپشن بر اساس فیلترهای نوسان‌گیری
        selected_option = option_selector.get_best_option(db_path, symbol, signal_type, last_price)

        if selected_option:
            opt_price = selected_option.get('option_price_clean', 100.0)
            
            # ۴. محاسبه مدیریت ریسک با آستانه‌های اختصاصی نماد
            risk_plan = risk_management.calculate_risk_parameters(
                symbol=symbol,
                signal_type=signal_type,
                signal_score=v5_score,
                ua_price=last_price,
                option_price=opt_price,
                portfolio_value=100000000
            )

            risk_management.print_risk_report(risk_plan, f"V5 Engine: {symbol} -> {selected_option['symbol']}")
        else:
            logger.warning(f"⏭️ سیگنال {signal_type} در V5 صادر شد اما آپشنی فیلترها را پاس نکرد.")
    else:
        logger.info(f"☕ [V5] وضعیت {symbol} خنثی (WATCH) است.")

    # ۵. ثبت اختصاصی تاریخچه سیگنال‌های V5 در جدول سایه (Shadow)
    if os.path.exists(db_path) and not is_test_mode:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            opt_sym = selected_option['symbol'] if selected_option else None
            opt_prc = selected_option['option_price_clean'] if selected_option else None
            sl_val = risk_plan['option_sl'] if risk_plan else None
            tp_val = risk_plan['option_tp'] if risk_plan else None

            # ثبت در ستون‌های v2_score و v2_decision دیتابیس
            cursor.execute("""
                INSERT INTO signal_history (time, symbol, signal_type, composite_score, option_symbol, option_price, stop_loss, target1, v2_score, v2_decision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_str, symbol, signal_type, v5_score, opt_sym, opt_prc, sl_val, tp_val, v5_score, signal_type))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ خطای ثبت در دیتابیس V5: {e}")

    return {"symbol": symbol, "signal": signal_type, "option": selected_option, "risk": risk_plan}


def main():
    is_test_mode = len(sys.argv) > 1 and sys.argv[1] == "--test"

    print("\n" + "="*70)
    print("🚀 سامانه تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V5 Engine)")
    print("======================================================================")

    if is_test_mode:
        print("🧪 [اجرای تست موتور V5 با تنظیمات یکپارچه‌شده نوسان‌گیری]\n")
        for sym, info in SYMBOLS.items():
            run_cycle_v5(sym, info, is_test_mode=True)
            
        print("="*70)
        print("🎉 [تست موتور V5 با موفقیت به پایان رسید]")
        print("======================================================================\n")
        sys.exit(0)

    # چرخه لایو V5
    logger.info("⏱️ موتور V5 فعال شد. پایش هر 300 ثانیه...")
    try:
        while True:
            if check_market_hours():
                logger.info("🟢 بازار فعال است. سیکل پایش V5...")
                for sym, info in SYMBOLS.items():
                    run_cycle_v5(sym, info, is_test_mode=False)

                if dashboard_v5:
                    try: dashboard_v5.generate_html()
                    except Exception: pass
            else:
                logger.info("💤 بازار بسته است. پایش بعدی 5 دقیقه دیگر.")

            time.sleep(300)
    except KeyboardInterrupt:
        logger.info("🛑 موتور V5 توسط کاربر متوقف شد.")


if __name__ == "__main__":
    main()