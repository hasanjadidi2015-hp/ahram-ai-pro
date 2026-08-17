# -*- coding: utf-8 -*-
"""
AHRAM AI - SIGNAL ENGINE  (نسخه‌ی مقاوم)

ربات نوسان‌گیری اپشن اهرم - فقط سیگنال می‌دهد (معامله نمی‌کند).
هر مرحله مستقل اجرا می‌شود؛ اگر یک بخش خطا دهد، بقیه همچنان کار می‌کنند.

روش اجرا:
    python ahram_signal.py
"""
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config
from database import create_database
from collector import collect
from strategy import Strategy
from option_selector import OptionSelector
from option_engine import compute_historical_volatility

# منبع داده‌ی اپشن:
#  اولویت با live_option_feed (algotik_tse) که Open Interest هم می‌دهد.
#  اگر در دسترس نبود، از collect_options (MarketWatchInit سبک) استفاده می‌کنیم.
try:
    from live_option_feed import fetch_and_save_options
    _HAS_LIVE_FEED = True
except Exception:
    _HAS_LIVE_FEED = False

try:
    from option_collector import collect_options
    _HAS_LIGHT_COLLECTOR = True
except Exception:
    _HAS_LIGHT_COLLECTOR = False


def _fetch_option_data():
    """دریافت داده‌ی اپشن: اول algotik_tse، بعد MarketWatchInit."""
    if _HAS_LIVE_FEED:
        try:
            print("[OPTION DATA] استفاده از algotik_tse (با Open Interest)...")
            fetch_and_save_options()
            return
        except Exception as e:
            print("[OPTION DATA] خطا در algotik_tse:", e)

    if _HAS_LIGHT_COLLECTOR:
        try:
            print("[OPTION DATA] استفاده از MarketWatchInit (سبک، بدون OI)...")
            collect_options()
            return
        except Exception as e:
            print("[OPTION DATA] خطا در MarketWatchInit:", e)

    print("[OPTION DATA] هیچ منبع داده‌ای در دسترس نیست.")


def run_once():
    print("\n" + "=" * 60)
    print("AHRAM AI - SIGNAL ENGINE   ",
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    # 1) دیتابیس
    try:
        create_database()
    except Exception as e:
        print("DB ERROR:", e)

    # 2) نوسان‌پذیری تاریخی
    try:
        hv = compute_historical_volatility()
        if hv:
            print(f"[VOL] نوسان‌پذیری تاریخی اهرم: {round(hv * 100, 1)}%")
        else:
            print("[VOL] نوسان تاریخی موجود نیست -> از مقدار تنظیمات استفاده می‌شود")
    except Exception as e:
        print("[VOL] ERROR:", e)

    # 3) قیمت سهم
    try:
        collect()
    except Exception as e:
        print("STOCK DATA ERROR:", e)

    # 4) داده‌ی اپشن
    _fetch_option_data()

    # 5) تحلیل تکنیکال سهم
    stock_action = "WATCH"
    stock_confidence = 0
    stock_score = 0
    price = 0
    try:
        strategy = Strategy()
        result = strategy.analyze()
        try:
            strategy.close()
        except Exception:
            pass

        if result is None:
            print("=" * 60)
            print("اطلاعات قیمت کافی نیست.")
            print("اول این را اجرا کن:  python history_loader.py")
            print("=" * 60)
            return

        # استراتژی V10 یک تاپل ۴تایی برمی‌گرداند
        stock_action, stock_confidence, stock_score, price = result
    except Exception as e:
        print("STRATEGY ERROR:", e)

    # 6) تحلیل اپشن
    option_decision = None
    try:
        selector = OptionSelector()
        option_decision = selector.run(
            stock_action=stock_action,
            stock_confidence=stock_confidence,
            current_stock_price=price if price else None,
        )
        selector.close()
    except Exception as e:
        print("OPTION SELECTOR ERROR:", e)

    # 7) سیگنال نهایی
    print("\n" + "#" * 60)
    print("                   ★  SIGNAL RESULT  ★")
    print("#" * 60)
    print(f"  اهرم PRICE        : {price}")
    print(f"  STOCK ACTION      : {stock_action}")
    print(f"  STOCK CONFIDENCE  : {stock_confidence} %")
    print(f"  STOCK SCORE       : {stock_score}")

    if option_decision:
        print("-" * 60)
        print(f"  OPTION            : {option_decision.get('symbol')}  "
              f"(strike {option_decision.get('strike_price')})")
        print(f"  OPTION ACTION     : {option_decision.get('action')}")
        print(f"  OPTION CONFIDENCE : {option_decision.get('confidence')} %")
        print(f"  MARKET PRICE      : {option_decision.get('option_price')}")
        print(f"  FAIR VALUE (BS)   : {option_decision.get('fair_value')}")
        print(f"  VALUATION         : {option_decision.get('valuation')}")
        print(f"  DELTA             : {option_decision.get('delta')}")
        print(f"  PROB OF PROFIT    : {option_decision.get('probability_of_profit')} %")

        action = str(option_decision.get("action", ""))
        print("-" * 60)
        if action == "BUY OPTION":
            print("  >>> SIGNAL: ★★★ BUY OPTION (سیگنال خرید) ★★★")
        elif "WATCH" in action:
            print("  >>> SIGNAL: ● WATCH (تحت نظر) ●")
        else:
            print("  >>> SIGNAL: ○ WAIT / NO TRADE (صبر کن) ○")
        print("-" * 60)
        print("  دلایل:")
        for r in option_decision.get("reasons", []):
            print("     -", r)
    else:
        print("-" * 60)
        print("  OPTION: داده‌ای برای تحلیل نیست")
        print("  >>> SIGNAL: ○ WAIT (صبر کن) ○")

    print("#" * 60)


if __name__ == "__main__":
    run_once()
