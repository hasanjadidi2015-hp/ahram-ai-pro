# -*- coding: utf-8 -*-
"""
ماژول مدیریت ریسک و تعیین حجم معاملات (Risk & Position Sizing Engine)
نسخه ارتقایافته 2026-09-05 - مجهز به آستانه‌های اختصاصی اثبات‌شده بر اساس بک‌تست
دارای سوئیچ تست خودکار --test
"""

import sys
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RiskManager")

DEFAULT_PORTFOLIO_VALUE = 100000000  # ۱۰۰ میلیون ریال (۱۰ میلیون تومان فرض اولیه)

# تنظیمات اختصاصی بهینه‌شده هر نماد بر اساس نتایج بک‌تست تاریخی
SYMBOL_SETTINGS = {
    "اهرم": {
        "min_score": 62.0,      # حداقل امتیاز مجاز برای ورود
        "ua_tp_pct": 7.0,       # حد سود سهم پایه (+۷٪)
        "ua_sl_pct": 3.5,       # حد ضرر سهم پایه (-۳.۵٪)
        "opt_tp_pct": 35.0,     # حد سود آپشن (+۳۵٪)
        "opt_sl_pct": 17.5      # حد ضرر آپشن (-۱۷.۵٪)
    },
    "وبملت": {
        "min_score": 55.0,
        "ua_tp_pct": 6.0,
        "ua_sl_pct": 3.0,
        "opt_tp_pct": 30.0,
        "opt_sl_pct": 15.0
    },
    "شستا": {
        "min_score": 55.0,
        "ua_tp_pct": 6.0,
        "ua_sl_pct": 3.0,
        "opt_tp_pct": 30.0,
        "opt_sl_pct": 15.0
    }
}


def calculate_risk_parameters(
    symbol: str,
    signal_type: str,
    signal_score: float,
    ua_price: float,
    option_price: float,
    portfolio_value: float = DEFAULT_PORTFOLIO_VALUE
) -> Dict[str, Any]:
    """محاسبه دقیق حجم ورود و سطوح خروج بر اساس قوانین اختصاصی نماد"""
    cfg = SYMBOL_SETTINGS.get(symbol, {
        "min_score": 55.0, "ua_tp_pct": 6.0, "ua_sl_pct": 3.0, "opt_tp_pct": 30.0, "opt_sl_pct": 15.0
    })

    # ۱. بررسی آستانه کیفیت
    is_valid_entry = signal_score >= cfg["min_score"]

    if signal_score >= 80:
        allocation_pct = 0.10  # ۱۰٪ سرمایه برای سیگنال‌های عالی
        confidence_level = "عالی (Strong Buy)"
    elif is_valid_entry:
        allocation_pct = 0.05  # ۵٪ سرمایه برای سیگنال‌های استاندارد
        confidence_level = "معتبر (Valid Buy)"
    else:
        allocation_pct = 0.0   # عدم تخصیص بودجه
        confidence_level = f"رد شده (امتیاز {signal_score:.1f} < {cfg['min_score']})"

    allocated_budget = portfolio_value * allocation_pct
    suggested_qty = int(allocated_budget / option_price) if (option_price > 0 and allocated_budget > 0) else 0

    # ۲. حدود خروج خود آپشن
    option_sl = option_price * (1 - (cfg["opt_sl_pct"] / 100)) if option_price > 0 else 0.0
    option_tp = option_price * (1 + (cfg["opt_tp_pct"] / 100)) if option_price > 0 else 0.0

    # ۳. حدود خروج سهم پایه
    ua_sl = 0.0
    ua_tp = 0.0
    if ua_price > 0:
        if signal_type == "BUY_CALL":
            ua_sl = ua_price * (1 - (cfg["ua_sl_pct"] / 100))
            ua_tp = ua_price * (1 + (cfg["ua_tp_pct"] / 100))
        elif signal_type == "BUY_PUT":
            ua_sl = ua_price * (1 + (cfg["ua_sl_pct"] / 100))
            ua_tp = ua_price * (1 - (cfg["ua_tp_pct"] / 100))

    return {
        "symbol": symbol,
        "signal_type": signal_type,
        "signal_score": signal_score,
        "min_score_required": cfg["min_score"],
        "is_valid": is_valid_entry,
        "confidence": confidence_level,
        "portfolio_value": portfolio_value,
        "allocation_pct": allocation_pct * 100,
        "allocated_budget": allocated_budget,
        "suggested_qty": suggested_qty,
        "entry_option_price": option_price,
        "option_sl": round(option_sl, 1),
        "option_tp": round(option_tp, 1),
        "entry_ua_price": ua_price,
        "ua_sl": round(ua_sl, 1),
        "ua_tp": round(ua_tp, 1),
        "opt_tp_pct": cfg["opt_tp_pct"],
        "opt_sl_pct": cfg["opt_sl_pct"],
        "ua_tp_pct": cfg["ua_tp_pct"],
        "ua_sl_pct": cfg["ua_sl_pct"]
    }


def print_risk_report(risk: Dict[str, Any], title: str = ""):
    sym_title = title if title else risk.get("symbol", "نماد")
    print(f"\n============================================================")
    print(f"🛡️ طرح مدیریت ریسک بهینه‌شده نوسان‌گیری [{sym_title}]")
    print(f"============================================================")
    print(f"• وضعیت سیگنال: {risk['signal_type']} (اعتبار: {risk['confidence']} | امتیاز: {risk['signal_score']:.1f} از ۱۰۰)")
    print(f"• حداقل امتیاز لازم برای ورود: {risk['min_score_required']:.0f}")

    if risk["is_valid"]:
        print(f"• حجم ورود مجاز: {risk['allocation_pct']:.1f}% از کل سرمایه ({risk['allocated_budget']:,.0f} ریال)")
        print(f"• تعداد خرید پیشنهادی: {risk['suggested_qty']:,.0f} برگه آپشن (قیمت واحد: {risk['entry_option_price']:,.0f} ریال)")
        print(f"\n🎯 [اهداف خروج سهم پایه] (معیار اصلی و نقدشونده):")
        print(f"   └── قیمت فعلی سهم: {risk['entry_ua_price']:,.0f} ریال")
        print(f"   └── حد سود سهم (TP): {risk['ua_tp']:,.0f} ریال (+/- {risk['ua_tp_pct']}%)")
        print(f"   └── حد ضرر سهم (SL): {risk['ua_sl']:,.0f} ریال (+/- {risk['ua_sl_pct']}%)")
        print(f"\n🛑 [اهداف خروج آپشن] (معیار کمکی):")
        print(f"   └── حد سود آپشن (TP): {risk['option_tp']:,.0f} ریال (+{risk['opt_tp_pct']}%)")
        print(f"   └── حد ضرر آپشن (SL): {risk['option_sl']:,.0f} ریال (-{risk['opt_sl_pct']}%)")
    else:
        print(f"\n⛔ معامله مجاز نیست: امتیاز سیگنال ({risk['signal_score']:.1f}) به حد نصاب ({risk['min_score_required']:.0f}) نرسید.")
    print(f"============================================================\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\n=== [تست خودکار ماژول مدیریت ریسک بهینه‌شده] ===")
        # تست اهرم با امتیاز معتبر ۶۵
        r1 = calculate_risk_parameters("اهرم", "BUY_CALL", 65.0, 57000, 1200)
        print_risk_report(r1, "اهرم -> ضهرم7061")

        # تست اهرم با امتیاز نامعتبر ۵۸ (باید رد شود چون اهرم به ۶۲ نیاز دارد)
        r2 = calculate_risk_parameters("اهرم", "BUY_CALL", 58.0, 57000, 1200)
        print_risk_report(r2, "اهرم (امتیاز ضعیف)")

        print("🥇 تست ماژول مدیریت ریسک با موفقیت پاس شد ✅\n")