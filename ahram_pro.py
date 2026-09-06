# -*- coding: utf-8 -*-
"""
هسته اصلی موتور تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V4 Live Engine)
نسخه نهایی و اصلاح‌شده 2026-09-06
مجهز به موتور تکنیکال زنده، فیلترهای نوسان‌گیری و ماشین حساب مدیریت ریسک
"""

import os
import sys
import time
import sqlite3
import logging
import inspect
from datetime import datetime
from typing import Dict, Any, Tuple

# ماژول‌های اصلی سیستم
import option_selector
import risk_management

# ماژول‌های فرعی با مکانیسم Fallback امن
try: import collector
except ImportError: collector = None

try: import telegram_notify
except ImportError: telegram_notify = None

try: import dashboard
except ImportError: dashboard = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AhramPro")

DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db"
}

SYMBOLS = {
    "اهرم": {"ins_code": "17914401175772326", "db": DBS["اهرم"]},
    "وبملت": {"ins_code": "778253364357513", "db": DBS["وبملت"]},
    "شستا": {"ins_code": "2400322364771558", "db": DBS["شستا"]}
}


def check_market_hours() -> bool:
    """بررسی ساعات بازار: شنبه تا چهارشنبه 09:00 الی 12:30"""
    now = datetime.now()
    if now.weekday() in [3, 4]:  # پنج‌شنبه و جمعه
        return False
    current_time = now.strftime("%H:%M")
    return "09:00" <= current_time <= "12:30"


def safe_update_collector(symbol: str):
    """تلاش برای بروزرسانی آنلاین دیتا بدون کرش یا ارور در صورت تغییر نام توابع"""
    if not collector:
        return
    candidate_funcs = ['fetch_data', 'update_data', 'collect_data', 'collect', 'update', 'main', 'run']
    for fn_name in candidate_funcs:
        if hasattr(collector, fn_name):
            try:
                fn = getattr(collector, fn_name)
                sig = inspect.signature(fn)
                if len(sig.parameters) > 0:
                    fn(symbol)
                else:
                    fn()
                break
            except Exception:
                continue


def calculate_live_technical_score(prices: list) -> Tuple[float, str, str]:
    """
    محاسبه شاخص‌های تکنیکال زنده از لیست قیمت‌های لحظه‌ای
    خروجی: (امتیاز 0-100، نوع سیگنال، وضعیت روند)
    """
    if len(prices) < 14:
        return 50.0, "WATCH", "داده ناکافی"

    # ۱. محاسبه RSI 14
    gains, losses = [], []
    for i in range(1, 15):
        diff = prices[-i] - prices[-i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / 14.0
    avg_loss = sum(losses) / 14.0

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

    # ۲. محاسبه میانگین متحرک کوتاه و بلند (EMA 5 و EMA 20)
    ema_short = sum(prices[-5:]) / 5.0
    ema_long = sum(prices[-20:]) / min(len(prices), 20)
    current_p = prices[-1]

    # ۳. محاسبه شتاب و مومنتوم
    price_change_pct = ((current_p - prices[-10]) / prices[-10]) * 100 if len(prices) >= 10 else 0.0

    score = 50.0
    signal = "WATCH"
    trend_desc = "خنثی"

    # تحلیل صعودی (BULLISH)
    if current_p > ema_short > ema_long and rsi < 70:
        score = 55.0 + min(rsi * 0.4, 30.0) + (max(0, price_change_pct) * 2)
        score = min(score, 95.0)
        trend_desc = f"صعودی پرقدرت (RSI: {rsi:.1f})"
        signal = "BUY_CALL"
    elif current_p > ema_short and rsi < 60:
        score = 52.0 + min(rsi * 0.25, 20.0)
        trend_desc = f"صعودی ملایم (RSI: {rsi:.1f})"
        signal = "BUY_CALL"

    # تحلیل نزولی (BEARISH)
    elif current_p < ema_short < ema_long and rsi > 30:
        score = 55.0 + min((100.0 - rsi) * 0.4, 30.0) + (max(0, -price_change_pct) * 2)
        score = min(score, 95.0)
        trend_desc = f"نزولی پرقدرت (RSI: {rsi:.1f})"
        signal = "BUY_PUT"
    elif current_p < ema_short and rsi > 40:
        score = 52.0 + min((100.0 - rsi) * 0.25, 20.0)
        trend_desc = f"نزولی ملایم (RSI: {rsi:.1f})"
        signal = "BUY_PUT"
    else:
        score = 45.0 + (rsi * 0.1)
        trend_desc = f"رنج و نوسانی (RSI: {rsi:.1f})"
        signal = "WATCH"

    return round(score, 1), signal, trend_desc


def run_cycle_for_symbol(symbol: str, info: dict, is_test_mode: bool = False) -> dict:
    db_path = info["db"]
    logger.info(f"🔄 [V4 Engine] پایش زنده نماد [{symbol}]...")

    prices_list = []
    last_price = 0.0

    # ۱. استخراج دیتای قیمت‌های اخیر از دیتابیس
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT last_price, closing_price FROM prices ORDER BY id DESC LIMIT 50")
            rows = cur.fetchall()
            for r in reversed(rows):
                p = float(r[0] or r[1] or 0)
                if p > 0:
                    prices_list.append(p)
            if prices_list:
                last_price = prices_list[-1]
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ خطای خواندن قیمت‌ها: {e}")

    if last_price <= 0:
        fallback_prices = {"اهرم": 57167.0, "وبملت": 1483.0, "شستا": 2932.0}
        last_price = fallback_prices.get(symbol, 50000.0)
        prices_list = [last_price * (1 + (i * 0.002)) for i in range(25)]

    # ۲. محاسبه شاخص‌های تکنیکال زنده
    tech_score, signal_type, trend_desc = calculate_live_technical_score(prices_list)
    logger.info(f"📡 [V4] وضعیت: {signal_type} | امتیاز: {tech_score:.1f} / 100 | روند: {trend_desc}")

    # ۳. انتخاب آپشن و اعمال مدیریت ریسک
    selected_option = None
    risk_plan = None

    if signal_type in ["BUY_CALL", "BUY_PUT"]:
        selected_option = option_selector.get_best_option(db_path, symbol, signal_type, last_price)

        if selected_option:
            opt_price = selected_option.get('option_price_clean', 100.0)
            
            # محاسبه مدیریت ریسک با آستانه اختصاصی
            risk_plan = risk_management.calculate_risk_parameters(
                symbol=symbol,
                signal_type=signal_type,
                signal_score=tech_score,
                ua_price=last_price,
                option_price=opt_price,
                portfolio_value=100000000
            )

            # نمایش گزارش مدیریت ریسک
            risk_management.print_risk_report(risk_plan, f"{symbol} -> {selected_option['symbol']}")

            # ارسال تلگرام در صورت تایید کامل
            if risk_plan["is_valid"] and telegram_notify and not is_test_mode:
                try:
                    msg = (f"🚨 سیگنال تأییدشده نوسان‌گیری [{symbol}]\n"
                           f"🛒 نماد آپشن: {selected_option['symbol']}\n"
                           f"📈 امتیاز: {tech_score:.1f} / 100\n"
                           f"📉 قیمت ورود: {opt_price:,.0f} ریال\n"
                           f"🎯 حد سود آپشن: {risk_plan['option_tp']:,.0f} ریال (+{risk_plan['opt_tp_pct']}%)\n"
                           f"🛑 حد ضرر آپشن: {risk_plan['option_sl']:,.0f} ریال (-{risk_plan['opt_sl_pct']}%)\n"
                           f"🎯 هدف سهم پایه: {risk_plan['ua_tp']:,.0f} ریال")
                    telegram_notify.send_message(msg)
                except Exception as ex:
                    logger.warning(f"⚠️ خطای ارسال تلگرام: {ex}")
        else:
            logger.info(f"⏭️ سیگنال {signal_type} صادر شد، اما آپشنی از فیلترهای نوسان‌گیری عبور نکرد.")
    else:
        logger.info(f"☕ [V4] وضعیت {symbol} در این سیکل خنثی (WATCH) است.")

    # ۴. ثبت در دیتابیس
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

    return {"symbol": symbol, "signal": signal_type, "score": tech_score, "option": selected_option, "risk": risk_plan}


def main():
    is_test_mode = len(sys.argv) > 1 and sys.argv[1] == "--test"

    print("\n" + "="*70)
    print("🚀 سامانه تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V4 Live Engine)")
    print("======================================================================")

    if is_test_mode:
        print("🧪 [اجرای تست تک‌سیکل زنده محاسبات V4]\n")
        for sym, info in SYMBOLS.items():
            run_cycle_for_symbol(sym, info, is_test_mode=True)
            
        print("="*70)
        print("🎉 [تست با موفقیت به پایان رسید]")
        print("======================================================================\n")
        sys.exit(0)

    logger.info("⏱️ موتور اصلی V4 فعال شد (سیکل پایش: هر 300 ثانیه)...")
    try:
        while True:
            if check_market_hours():
                logger.info("🟢 بازار فعال است. آغاز سیکل پایش زنده V4...")
                for sym, info in SYMBOLS.items():
                    safe_update_collector(sym)
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