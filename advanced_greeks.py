# -*- coding: utf-8 -*-
"""Advanced option Greeks for risk description only.

این ماژول هیچ سیگنال یا confidence را تغییر نمی‌دهد. خروجی آن صرفاً برای
نمایش، ثبت در details و جمع‌آوری داده در بازار آپشن ایران است.
"""
import math


def _pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs(S, K, T, r, sigma, option_type="CALL"):
    if min(S, K, T, sigma) <= 0:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0}
    d1 = (math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    cdf = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    delta = cdf(d1) if option_type == "CALL" else cdf(d1) - 1
    gamma = _pdf(d1) / (S * sigma * math.sqrt(T))
    # vega per 1 percentage point IV, consistent with option_engine.py
    vega = S * _pdf(d1) * math.sqrt(T) / 100.0
    return {"delta": delta, "gamma": gamma, "vega": vega}


def calculate(stock_price, strike_price, days_to_expire, volatility, risk_free, option_type="CALL"):
    """محاسبه عددی پایدار Greeks پیشرفته.

    charm_1d و color_1d اثر گذشت یک روز تقویمی را نشان می‌دهند.
    vanna_1pct اثر تغییر یک واحد درصد IV روی Delta است.
    volga_1pct تغییر Vega (per 1% IV) با یک واحد درصد تغییر IV است.
    """
    empty = {"available": False, "risk_level": "UNKNOWN", "reasons": ["داده کافی نیست"]}
    try:
        S, K = float(stock_price), float(strike_price)
        dte, sigma, r = int(days_to_expire), float(volatility), float(risk_free)
        if S <= 0 or K <= 0 or dte < 2 or sigma <= 0:
            return empty
        T = dte / 365.0
        one_day = 1.0 / 365.0
        base = _bs(S, K, T, r, sigma, option_type)
        tomorrow = _bs(S, K, max(T - one_day, 1e-8), r, sigma, option_type)
        bump = 0.01
        low_sigma, high_sigma = max(0.01, sigma - bump), sigma + bump
        low = _bs(S, K, T, r, low_sigma, option_type)
        high = _bs(S, K, T, r, high_sigma, option_type)

        charm = tomorrow["delta"] - base["delta"]
        color = tomorrow["gamma"] - base["gamma"]
        color_pct = (color / base["gamma"] * 100) if base["gamma"] else 0.0
        vanna = (high["delta"] - low["delta"]) / 2.0  # Delta change per 1 IV point
        volga = (high["vega"] - low["vega"]) / 2.0   # Vega change per 1 IV point

        reasons = []
        points = 0
        if dte <= 10:
            points += 1; reasons.append("سررسید نزدیک")
        if abs(charm) >= 0.02:
            points += 1; reasons.append("Charm بالا: Delta با گذر زمان تغییر محسوسی دارد")
        if abs(color_pct) >= 20:
            points += 1; reasons.append("Color بالا: Gamma با گذر زمان ناپایدار است")
        if abs(vanna) >= 0.005:
            points += 1; reasons.append("Vanna بالا: Delta به تغییر IV حساس است")
        if abs(volga) >= max(0.02, abs(base["vega"]) * 0.20):
            points += 1; reasons.append("Volga بالا: حساسیت IV می‌تواند تغییر کند")
        level = "LOW" if points <= 1 else ("MEDIUM" if points <= 3 else "HIGH")
        if not reasons:
            reasons = ["ریسک یونانی‌های پیشرفته در محدوده عادی است"]
        return {
            "available": True, "risk_level": level, "risk_points": points,
            "charm_1d": round(charm, 5), "color_1d": round(color, 8),
            "color_pct_1d": round(color_pct, 1), "vanna_1pct": round(vanna, 5),
            "volga_1pct": round(volga, 5), "dte": dte, "reasons": reasons,
        }
    except Exception:
        return empty
