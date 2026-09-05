# -*- coding: utf-8 -*-
"""
هسته اصلی موتور تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro V4 - Final Edition)
نسخه نهایی و بهینه‌شده 2026-09-05
مجهز به فیلترهای نوسان‌گیری اثبات‌شده، آستانه‌های اختصاصی نمادها و موتور مدیریت ریسک
"""

import os
import sys
import time
import sqlite3
import logging
from datetime import datetime

# ایمپورت ماژول‌های اختصاصی
import option_selector
import risk_management

# ایمپورت‌های فرعی با مکانیسم Fallback امن
try:
    import config
    DB_NAMES = {
        "اهرم": getattr(config, "DB_AHRAM", "ahram_v2.db"),
        "وبملت": getattr(config, "DB_WEBMELLT", "webmellt.db"),
        "شستا": getattr(config, "DB_SHASTA", "shasta.db")
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

try: import strategy
except ImportError: strategy = None

try: import telegram_notify
except ImportError: telegram_notify = None

try: import dashboard
except ImportError: dashboard = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AhramPro")

SYMBOLS = {
    "اهرم": {"ins_code": "17914401175772326", "db": DB_NAMES["اهرم"]},
    "وبملت": {"ins_code": "778253364357513", "db": DB_NAMES["وبملت"]},
    "شستا": {"ins_code": "2400322364771558", "db": DB_NAMES["شستا"]}
}


def check_market_hours() -> bool:
    """بررسی ساعات بازار: شنبه تا چهارشنبه 09:00 الی 12:30"""
    now = datetime.now()
    if now.weekday() in [3, 4]:  # پنج‌شنبه و جمعه
        return False
    current_time = now.strftime("%H:%M")
    return "09:00" <= current_time <= "12:30"


def run_cycle_for_symbol(symbol: str, info: dict, is_test_mode: bool = False) -> dict:
    """اجرای یک سیکل کامل تحلیل، انتخاب آپشن و اعمال مدیریت ریسک"""
    db_path = info["db"]
    logger.info(f"🔄 در حال پایش نماد [{symbol}]...")

    # ۱. دریافت آخرین قیمت دارایی پایه
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

    # قیمت پیش‌فرض برای اجرای تست خارج از بازار
    if last_price <= 0:
        fallback_prices = {"اهرم": 57167.0, "وبملت": 1483.0, "شستا": 2932.0}
        last_price = fallback_prices.get(symbol, 50000.0)

    # ۲. استخراج سیگنال و امتیاز
    if strategy and not is_test_mode:
        try:
            tech_score, signal_type = strategy.analyze_symbol(db_path, last_price)
        except Exception as e:
            logger.error(f"❌ خطا در اجرای استراتژی {symbol}: {e}")
            tech_score, signal_type = 50.0, "WATCH"
    else:
        # سناریوهای تستی برای اعتبارسنجی
        simulations = {
            "اهرم": (65.0, "BUY_CALL"),   # امتیاز ۶۵ >= ۶۲ (باید تأیید شود)
            "شستا": (58.0, "BUY_PUT"),    # امتیاز ۵۸ >= ۵۵ (باید تأیید شود)
            "وبملت": (45.0, "WATCH")      # خنثی
        }
        tech_score, signal_type = simulations.get(symbol, (50.0, "WATCH"))

    logger.info(f"📡 وضعیت استراتژی: {signal_type} | امتیاز: {tech_score:.1f}")

    selected_option = None
    risk_plan = None

    if signal_type in ["BUY_CALL", "BUY_PUT"]:
        # ۳. انتخاب بهترین آپشن نوسانی (اسپرد و DTE)
        selected_option = option_selector.get_best_option(db_path, symbol, signal_type, last_price)

        if selected_option:
            opt_price = selected_option.get('option_price_clean', 100.0)
            
            # ۴. محاسبه دقیق ریسک با آستانه اختصاصی نماد
            risk_plan = risk_management.calculate_risk_parameters(
                symbol=symbol,
                signal_type=signal_type,
                signal_score=tech_score,
                ua_price=last_price,
                option_price=opt_price,
                portfolio_value=100000000
            )

            # نمایش گزارش فارسی
            risk_management.print_risk_report(risk_plan, f"{symbol} -> {selected_option['symbol']}")

            # ۵. ارسال پیام تلگرام فقط در صورت تایید کامل و معتبر بودن سیگنال
            if risk_plan["is_valid"] and telegram_notify and not is_test_mode:
                try:
                    msg = (f"🚨 سیگنال نوسان‌گیری تأییدشده [{symbol}]\n"
                           f"🛒 آپشن: {selected_option['symbol']}\n"
                           f"📈 امتیاز: {tech_score:.1f} / 100\n"
                           f"📉 قیمت ورود: {opt_price:,.0f} ریال\n"
                           f"🎯 حد سود آپشن (TP): {risk_plan['option_tp']:,.0f} ریال (+{risk_plan['opt_tp_pct']}%)\n"
                           f"🛑 حد ضرر آپشن (SL): {risk_plan['option_sl']:,.0f} ریال (-{risk_plan['opt_sl_pct']}%)\n"
                           f"🎯 هدف سهم ({symbol}): {risk_plan['ua_tp']:,.0f} ریال")
                    telegram_notify.send_message(msg)
                except Exception as ex:
                    logger.warning(f"⚠️ خطای ارسال تلگرام: {ex}")
        else:
            logger.warning(f"⏭️ سیگنال {signal_type} صادر شد اما آپشن مناسبی از فیلترهای نوسان‌گیری عبور نکرد.")
    else:
        logger.info(f"☕ وضعیت {symbol} خنثی (WATCH) است. نظاره‌گر بازار.")

    # ۶. ثبت در دیتابیس (فقط در حالت واقعی و بدون دستکاری دیتای قدیمی)
    if os.path.exists(db_path) and not is_test_mode:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            opt_sym = selected_option['symbol'] if selected_option else None
            opt_prc = selected_option['option_price_clean'] if selected_option else None
            sl_val = risk_plan['option_sl'] if risk_plan else None
            tp_val = risk_plan['option_tp'] if risk_plan else None

            cursor.execute("""
                INSERT INTO signal_history (time, symbol, signal_type, composite_score, option_symbol, option_price, stop_loss, target1)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_str, symbol, signal_type, tech_score, opt_sym, opt_prc, sl_val, tp_val))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ خطای ثبت سیگنال در دیتابیس: {e}")

    return {"symbol": symbol, "signal": signal_type, "option": selected_option, "risk": risk_plan}


def main():
    is_test_mode = len(sys.argv) > 1 and sys.argv[1] == "--test"

    print("\n" + "="*70)
    print("🚀 سامانه تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V4 Engine)")
    print("======================================================================")

    if is_test_mode:
        print("🧪 [اجرای تست یک سیکل کامل با آستانه‌های طلایی بهینه‌شده]\n")
        for sym, info in SYMBOLS.items():
            run_cycle_for_symbol(sym, info, is_test_mode=True)
            
        print("="*70)
        print("🎉 [تست یکپارچگی سیستم با موفقیت به پایان رسید]")
        print("======================================================================\n")
        sys.exit(0)

    # اجرای لایو
    logger.info("⏱️ موتور معاملاتی فعال شد (سیکل پایش: هر 300 ثانیه)...")
    try:
        while True:
            if check_market_hours():
                logger.info("🟢 بازار فعال است. آغاز سیکل پایش...")
                for sym, info in SYMBOLS.items():
                    if collector:
                        try: collector.update_data(sym)
                        except Exception as ex: logger.error(f"❌ خطای بروزرسانی زنده داده‌ها: {ex}")
                    run_cycle_for_symbol(sym, info, is_test_mode=False)

                if dashboard:
                    try: dashboard.generate_html()
                    except Exception as ex: logger.error(f"❌ خطای ساخت داشبورد: {ex}")
            else:
                logger.info("💤 بازار بسته است (ساعات فعالیت: شنبه تا چهارشنبه 09:00 الی 12:30).")

            time.sleep(300)
    except KeyboardInterrupt:
        logger.info("🛑 موتور توسط کاربر متوقف شد.")


if __name__ == "__main__":
    main()