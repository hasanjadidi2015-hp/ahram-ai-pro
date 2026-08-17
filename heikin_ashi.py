# -*- coding: utf-8 -*-
"""
================================================================
  🕯️  Heikin Ashi  —  نسخه‌ی ارتقایافته (با تحلیلِ شکلِ کندل)
================================================================
  رابط (با strategy.py سازگاره):
      calculate_heikin_ashi()  →  "BULLISH" / "BEARISH" / "NEUTRAL"
================================================================
"""
import numpy as np
import pandas as pd

# جزئیاتِ آخرین تحلیل (برای بازرسی/داشبورد)
LAST_RESULT = {}


class HeikinAshi:

    def __init__(self, candles):
        self.candles = candles.copy()
        self.strength = 50
        self.trend_strength = "NONE"   # STRONG / MODERATE / WEAK
        self.reversal_warning = False
        self.details = {}

    def analyze(self):
        c = self.candles
        if c.empty or len(c) < 5:
            return "NEUTRAL"

        o = c["open"].astype(float)
        h = c["high"].astype(float)
        low = c["low"].astype(float)
        cl = c["close"].astype(float)

        # ---------- محاسبه‌ی ۴ مؤلفه‌ی HA ----------
        ha_close = (o + h + low + cl) / 4.0

        ha_open_list = [(o.iloc[0] + cl.iloc[0]) / 2.0]
        for i in range(1, len(c)):
            ha_open_list.append((ha_open_list[i - 1] + ha_close.iloc[i - 1]) / 2.0)
        ha_open = pd.Series(ha_open_list, index=c.index)

        ha_high = pd.Series(np.maximum.reduce([h.values, ha_open.values, ha_close.values]), index=c.index)
        ha_low = pd.Series(np.minimum.reduce([low.values, ha_open.values, ha_close.values]), index=c.index)

        # ---------- تحلیل ۳ کندلِ اخیر ----------
        n = 3
        o3 = ha_open.tail(n)
        c3 = ha_close.tail(n)
        h3 = ha_high.tail(n)
        l3 = ha_low.tail(n)

        body = c3 - o3                       # مثبت=سبز، منفی=قرمز
        body_size = (body.abs())
        green = body > 0
        red = body < 0
        green_count = int(green.sum())
        red_count = int(red.sum())

        upper_wick = h3 - np.maximum(o3, c3)
        lower_wick = np.minimum(o3, c3) - l3

        avg_body = float(body_size.mean()) if body_size.mean() > 0 else 1e-9
        avg_upper = float(upper_wick.mean())
        avg_lower = float(lower_wick.mean())

        # نرم بودنِ کف/سقف (سایه‌ی مخالفِ کوچک)
        smooth_bottom = avg_lower < avg_body * 0.5   # روند صعودیِ نرم
        smooth_top = avg_upper < avg_body * 0.5      # روند نزولیِ نرم

        # doji: بدنه‌ی خیلی کوچک نسبت به سایه
        total_range = (h3 - l3).replace(0, 1e-9)
        body_ratio = body_size / total_range
        has_doji = bool((body_ratio < 0.3).any())

        # تغییر رنگ در ۲ کندلِ آخر (هشدار برگشتِ زودرس)
        color_flip = bool(green.iloc[-1] != green.iloc[-2])

        # ---------- تصمیم نهایی ----------
        if green_count == n and not has_doji:
            signal = "BULLISH"
            self.trend_strength = "STRONG" if smooth_bottom else "MODERATE"
        elif red_count == n and not has_doji:
            signal = "BEARISH"
            self.trend_strength = "STRONG" if smooth_top else "MODERATE"
        else:
            signal = "NEUTRAL"
            self.trend_strength = "WEAK"

        # هشدار برگشت: doji یا تغییرِ رنگ بعد از روند
        self.reversal_warning = has_doji or color_flip

        # ---------- امتیاز قدرت ----------
        s = 50
        s += (green_count - red_count) * 8       # جهتِ کندل‌ها
        if green_count == n:
            s += 6 if self.trend_strength == "STRONG" else 0
        if red_count == n:
            s -= 6 if self.trend_strength == "STRONG" else 0
        if has_doji:
            s = int(50 + (s - 50) * 0.4)         # doji → به‌سمت خنثی
        self.strength = max(0, min(100, s))

        # ---------- جزئیات ----------
        self.details = {
            "last_ha_open": round(float(ha_open.iloc[-1]), 2),
            "last_ha_close": round(float(ha_close.iloc[-1]), 2),
            "last_ha_high": round(float(ha_high.iloc[-1]), 2),
            "last_ha_low": round(float(ha_low.iloc[-1]), 2),
            "green_count_3": green_count,
            "red_count_3": red_count,
            "avg_body": round(avg_body, 2),
            "avg_upper_wick": round(avg_upper, 2),
            "avg_lower_wick": round(avg_lower, 2),
            "smooth_bottom": smooth_bottom,
            "smooth_top": smooth_top,
            "has_doji": has_doji,
            "color_flip": color_flip,
            "trend_strength": self.trend_strength,
            "reversal_warning": self.reversal_warning,
        }

        return signal


def analyze_heikin_ashi(candles):
    """تحلیلِ HA روی یه DataFrame از کندل‌ها (open/high/low/close)."""
    ha = HeikinAshi(candles)
    signal = ha.analyze()
    return signal, ha


def calculate_heikin_ashi(candle_minutes=15, min_candles=5, end_time=None):
    """رابطِ سازگار با strategy.py — کندل‌ها رو می‌سازه و تحلیل می‌کنه."""
    global LAST_RESULT
    try:
        from candle_builder import build_candles
        candles = build_candles(minutes=candle_minutes, end_time=end_time)
    except Exception as e:
        LAST_RESULT = {"error": str(e)}
        return "NEUTRAL"

    if candles is None or candles.empty or len(candles) < min_candles:
        LAST_RESULT = {"error": "کندل کافی نیست"}
        return "NEUTRAL"

    signal, ha = analyze_heikin_ashi(candles)
    LAST_RESULT = dict(ha.details)
    LAST_RESULT["signal"] = signal
    LAST_RESULT["strength"] = ha.strength
    return signal


if __name__ == "__main__":
    sig = calculate_heikin_ashi()
    print("=" * 55)
    print("Heikin Ashi (نسخه‌ی ارتقایافته)")
    print("=" * 55)
    print("سیگنال         :", sig)
    if LAST_RESULT and "error" not in LAST_RESULT:
        print("قدرت           :", LAST_RESULT.get("strength"), "/ 100")
        print("قدرت روند      :", LAST_RESULT.get("trend_strength"))
        print("سبز/قرمز (۳کندل):", LAST_RESULT.get("green_count_3"), "/", LAST_RESULT.get("red_count_3"))
        print("بدنه‌ی میانگین  :", LAST_RESULT.get("avg_body"))
        print("سایه‌ی بالا     :", LAST_RESULT.get("avg_upper_wick"))
        print("سایه‌ی پایین    :", LAST_RESULT.get("avg_lower_wick"))
        print("کفِ نرم؟        :", LAST_RESULT.get("smooth_bottom"))
        print("doji؟          :", LAST_RESULT.get("has_doji"))
        print("هشدار برگشت    :", "⚠️ بله" if LAST_RESULT.get("reversal_warning") else "خیر")
    else:
        print("نکته:", LAST_RESULT)
    print("=" * 55)