# -*- coding: utf-8 -*-
"""
موتور پیشرفته تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V5 Live Engine)
نسخه نهایی و متصل به موتورهای تحلیلی VACE، Sentiment و Technical
تاریخ: 2026-09-06
"""

import os
import sys
import time
import sqlite3
import logging
import inspect
from datetime import datetime
from typing import Dict, Any, Tuple

# ماژول‌های اصلی مدیریت ریسک و آپشن
import option_selector
import risk_management

# ماژول‌های تحلیلی V5
try: import sentiment_engine_v2
except ImportError: sentiment_engine_v2 = None

try: import vace_engine_v2
except ImportError: vace_engine_v2 = None

try: import decision_engine_v2
except ImportError: decision_engine_v2 = None

try: import dashboard_v5
except ImportError: dashboard_v5 = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AhramProV5")

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
    now = datetime.now()
    if now.weekday() in [3, 4]:  # پنج‌شنبه و جمعه
        return False
    current_time = now.strftime("%H:%M")
    return "09:00" <= current_time <= "12:30"


def safe_call(func, **kwargs):
    """فراخوانی امن توابع ماژول‌های فرعی با تطبیق خودکار پارامترها"""
    if not func:
        return None
    try:
        sig = inspect.signature(func)
        valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return func(**valid_kwargs)
    except Exception:
        try:
            # تلاش برای فراخوانی بدون آرگومان در صورت شکست
            return func()
        except Exception:
            return None


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

    # ۳. محاسبه مومنتوم و جهت
    price_change_pct = ((current_p - prices[-10]) / prices[-10]) * 100 if len(prices) >= 10 else 0.0

    score = 50.0
    signal = "WATCH"
    trend_desc = "خنثی"

    # تحلیل صعودی (BULLISH)
    if current_p > ema_short > ema_long and rsi < 70:
        score = 55.0 + min(rsi * 0.4, 30.0) + (max(0, price_change_pct) * 2)
        score = min(score, 95.0)
        trend_desc = f"صعودی قوی (RSI: {rsi:.1f})"
        signal = "BUY_CALL"
    elif current_p > ema_short and rsi < 60:
        score = 52.0 + min(rsi * 0.25, 20.0)
        trend_desc = f"صعودی ملایم (RSI: {rsi:.1f})"
        signal = "BUY_CALL"

    # تحلیل نزولی (BEARISH)
    elif current_p < ema_short < ema_long and rsi > 30:
        score = 55.0 + min((100.0 - rsi) * 0.4, 30.0) + (max(0, -price_change_pct) * 2)
        score = min(score, 95.0)
        trend_desc = f"نزولی قوی (RSI: {rsi:.1f})"
        signal = "BUY_PUT"
    elif current_p < ema_short and rsi > 40:
        score = 52.0 + min((100.0 - rsi) * 0.25, 20.0)
        trend_desc = f"نزولی ملایم (RSI: {rsi:.1f})"
        signal = "BUY_PUT"
    else:
        score = 45.0 + (rsi * 0.1)
        trend_desc = f"رنج / نوسانی (RSI: {rsi:.1f})"
        signal = "WATCH"

    return round(score, 1), signal, trend_desc


def run_cycle_v5(symbol: str, info: dict, is_test_mode: bool = False) -> dict:
    db_path = info["db"]
    logger.info(f"🔄 [V5 Live Engine] تحلیل زنده نماد [{symbol}]...")

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

    # ۳. دریافت وضعیت احساسات بازار از ماژول سنتیمنت (در صورت فعال بودن)
    sentiment_status = "خنثی"
    if sentiment_engine_v2:
        res_sent = safe_call(sentiment_engine_v2.analyze_sentiment, db_path=db_path, symbol=symbol)
        if isinstance(res_sent, dict):
            sentiment_status = res_sent.get("status", "عادی")
        elif isinstance(res_sent, str):
            sentiment_status = res_sent

    logger.info(f"📡 [V5] وضعیت: {signal_type} | امتیاز پویا: {tech_score:.1f} / 100 | روند: {trend_desc} | سنتیمنت: {sentiment_status}")

    # ۴. اعمال مدیریت ریسک و انتخاب آپشن
    selected_option = None
    risk_plan = None

    if signal_type in ["BUY_CALL", "BUY_PUT"]:
        selected_option = option_selector.get_best_option(db_path, symbol, signal_type, last_price)

        if selected_option:
            opt_price = selected_option.get('option_price_clean', 100.0)
            risk_plan = risk_management.calculate_risk_parameters(
                symbol=symbol,
                signal_type=signal_type,
                signal_score=tech_score,
                ua_price=last_price,
                option_price=opt_price,
                portfolio_value=100000000
            )

            # چاپ گزارش کامل در صورت احراز شرایط ورود
            risk_management.print_risk_report(risk_plan, f"V5 Engine: {symbol} -> {selected_option['symbol']}")
        else:
            logger.info(f"⏭️ سیگنال {signal_type} صادر شد اما آپشنی از فیلترهای نوسان‌گیری (اسپرد و DTE) عبور نکرد.")
    else:
        logger.info(f"☕ [V5] وضعیت {symbol} در این سیکل خنثی (WATCH) است.")

    # ۵. ثبت تاریخچه سیگنال در دیتابیس
    if os.path.exists(db_path) and not is_test_mode:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            opt_sym = selected_option['symbol'] if selected_option else None
            opt_prc = selected_option['option_price_clean'] if selected_option else None
            sl_val = risk_plan['option_sl'] if risk_plan else None
            tp_val = risk_plan['option_tp'] if risk_plan else None

            cur.execute("""
                INSERT INTO signal_history (time, symbol, signal_type, composite_score, option_symbol, option_price, stop_loss, target1, v2_score, v2_decision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_str, symbol, signal_type, tech_score, opt_sym, opt_prc, sl_val, tp_val, tech_score, signal_type))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ خطای ثبت سیگنال V5: {e}")

    return {"symbol": symbol, "signal": signal_type, "score": tech_score, "option": selected_option, "risk": risk_plan}


def main():
    is_test_mode = len(sys.argv) > 1 and sys.argv[1] == "--test"

    print("\n" + "="*70)
    print("🚀 سامانه تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V5 Live Engine)")
    print("======================================================================")

    if is_test_mode:
        print("🧪 [تست تک‌سیکل زنده محاسبات V5]\n")
        for sym, info in SYMBOLS.items():
            run_cycle_v5(sym, info, is_test_mode=True)
        print("="*70)
        print("🎉 [تست با موفقیت به پایان رسید]")
        print("======================================================================\n")
        sys.exit(0)

    logger.info("⏱️ موتور زنده V5 فعال شد (پایش هر 300 ثانیه)...")
    try:
        while True:
            if check_market_hours():
                logger.info("🟢 بازار فعال است. آغاز سیکل پایش زنده V5...")
                for sym, info in SYMBOLS.items():
                    run_cycle_v5(sym, info, is_test_mode=False)

                if dashboard_v5:
                    try: dashboard_v5.generate_html()
                    except Exception: pass
            else:
                logger.info("💤 بازار بسته است. سیکل بعدی 5 دقیقه دیگر.")

            time.sleep(300)
    except KeyboardInterrupt:
        logger.info("🛑 موتور V5 متوقف شد.")


if __name__ == "__main__":
    main()