# -*- coding: utf-8 -*-
"""
AHRAM OPTION ENGINE — بلک‌شولز + IV + Greeks + theta-aware
نسخه نهایی: نیوتن-رافسون + بایسکشن fallback
"""
import math
import sqlite3

import config


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def compute_historical_volatility(lookback=30):
    try:
        conn = sqlite3.connect(config.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT last_price FROM prices
            WHERE id IN (
                SELECT MAX(id) FROM prices GROUP BY substr(time, 1, 10)
            )
            ORDER BY id DESC
            LIMIT ?
            """,
            (lookback + 1,)
        )
        raw = [r[0] for r in cur.fetchall() if r[0] is not None]
        conn.close()
    except Exception:
        return None

    if len(raw) < 10:
        return None

    prices = [float(p) for p in reversed(raw)]
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))

    if len(returns) < 5:
        return None

    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    vol = math.sqrt(var)
    annualized = vol * math.sqrt(252)

    if annualized != annualized:
        return None

    annualized = max(0.20, min(2.50, annualized))
    return round(annualized, 4)


def get_dynamic_exit_thresholds(days_left):
    try:
        d = int(days_left)
    except (ValueError, TypeError):
        d = 30
    d = max(1, d)

    if d <= 7:
        return {"take_profit_pct": 15.0, "stop_loss_pct": -8.0}
    if d <= 21:
        return {"take_profit_pct": 25.0, "stop_loss_pct": -12.0}
    if d <= 45:
        return {"take_profit_pct": 40.0, "stop_loss_pct": -18.0}
    return {"take_profit_pct": 60.0, "stop_loss_pct": -25.0}


class OptionEngine:
    def __init__(self):
        pass

    def _bs(self, S, K, T, r, sigma, option_type="CALL"):
        empty = {"fair_value": 0.0, "delta": 0.0, "gamma": 0.0,
                 "theta": 0.0, "vega": 0.0, "d1": 0.0, "d2": 0.0}
        if T <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return empty
        try:
            d1 = (math.log(S / K) + (r + sigma ** 2 / 2.0) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)

            if option_type == "PUT":
                fair = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
                delta = _norm_cdf(d1) - 1.0
            else:
                fair = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
                delta = _norm_cdf(d1)

            gamma = _norm_pdf(d1) / (S * sigma * math.sqrt(T))

            if option_type == "PUT":
                theta = (-(S * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
                         + r * K * math.exp(-r * T) * _norm_cdf(-d2)) / 365.0
            else:
                theta = (-(S * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
                         - r * K * math.exp(-r * T) * _norm_cdf(d2)) / 365.0

            vega = (S * _norm_pdf(d1) * math.sqrt(T)) / 100.0
        except (ValueError, ZeroDivisionError):
            return empty

        return {"fair_value": fair, "delta": delta, "gamma": gamma,
                "theta": theta, "vega": vega, "d1": d1, "d2": d2}

    def _implied_vol(self, market_price, S, K, T, r, option_type="CALL"):
        """استخراج IV: نیوتن-رافسون (سریع) + fallback بایسکشن (تضمین converge)."""
        if market_price <= 0 or T <= 0 or S <= 0 or K <= 0:
            return None
        intrinsic = max(0, S - K) if option_type == "CALL" else max(0, K - S)
        if market_price < intrinsic * 0.95:
            return None

        sigma = 0.6
        best_sigma = sigma
        best_diff = abs(market_price)
        oscillating = False

        for i in range(100):
            g = self._bs(S, K, T, r, sigma, option_type)
            diff = g["fair_value"] - market_price

            if abs(diff) < abs(best_diff):
                best_diff = abs(diff)
                best_sigma = sigma

            if abs(diff) < 0.5:
                return sigma

            vega_raw = g["vega"] * 100.0
            if vega_raw < 1e-8:
                break

            step = diff / vega_raw
            sigma = sigma - step

            if sigma < 0.05:
                sigma = 0.05 + (0.05 - sigma) * 0.1
            elif sigma > 5.0:
                sigma = 5.0

            if i > 20 and abs(diff) > best_diff * 2:
                oscillating = True
                break

        # بایسکشن fallback (تضمین converge)
        lo, hi = 0.02, 5.0
        f_lo = self._bs(S, K, T, r, lo, option_type)["fair_value"] - market_price
        f_hi = self._bs(S, K, T, r, hi, option_type)["fair_value"] - market_price
        if f_lo <= 0 <= f_hi:
            for _ in range(60):
                mid = (lo + hi) / 2.0
                f_mid = self._bs(S, K, T, r, mid, option_type)["fair_value"] - market_price
                if abs(f_mid) < 0.5:
                    return mid
                if f_mid > 0:
                    hi = mid
                else:
                    lo = mid
            return (lo + hi) / 2.0

        # اگه نیوتن به جواب نزدیک و پایدار رسیده بود
        if not oscillating and best_diff < market_price * 0.1:
            return best_sigma
        return None

    def black_scholes(self, stock_price, strike_price, days_to_expire,
                      volatility=None, risk_free=None, option_type="CALL"):
        if volatility is None:
            volatility = config.BLACK_SCHOLES_VOL
        if risk_free is None:
            risk_free = config.RISK_FREE_RATE
        T = max(days_to_expire, 0) / 365.0
        g = self._bs(float(stock_price), float(strike_price), T,
                     float(risk_free), float(volatility), option_type)
        return {
            "fair_value": round(float(g["fair_value"]), 2),
            "delta": round(float(g["delta"]), 3),
            "gamma": round(float(g["gamma"]), 5),
            "theta": round(float(g["theta"]), 3),
            "vega": round(float(g["vega"]), 3),
        }

    def analyze(self, stock_price, strike_price, option_price,
                days_to_expire, option_type="CALL", volume=0, historical_volatility=None):
        stock_price = float(stock_price)
        strike_price = float(strike_price)
        option_price = float(option_price)
        days_to_expire = int(days_to_expire or 0)
        volume = float(volume or 0)
        r = config.RISK_FREE_RATE

        if historical_volatility and historical_volatility > 0:
            vol = historical_volatility
        else:
            vol = config.BLACK_SCHOLES_VOL
        volatility_used = vol

        T = max(days_to_expire, 0) / 365.0

        greeks = self._bs(stock_price, strike_price, T, r, vol, option_type)
        fair_value = greeks["fair_value"]

        if option_type == "PUT":
            intrinsic = max(0, strike_price - stock_price)
            break_even = strike_price - option_price
        else:
            intrinsic = max(0, stock_price - strike_price)
            break_even = strike_price + option_price
        time_value = option_price - intrinsic
        leverage = (stock_price / option_price) if option_price > 0 else 0

        data_quality = "OK"
        warnings = []
        if option_price < intrinsic:
            data_quality = "INVALID"
            warnings.append("OPTION BELOW INTRINSIC VALUE")
        if volume <= 0:
            warnings.append("LOW LIQUIDITY")

        if data_quality == "INVALID":
            valuation = "INVALID"
        elif option_price < fair_value:
            valuation = "UNDERVALUED"
        elif option_price > fair_value:
            valuation = "OVERVALUED"
        else:
            valuation = "FAIR"

        try:
            iv = self._implied_vol(option_price, stock_price, strike_price, T, r, option_type)
        except Exception:
            iv = None

        if iv is None or iv != iv or iv <= 0:
            implied_volatility = None
            iv_premium_ratio = None
            iv_crush_risk = False
            iv_bubble = "UNKNOWN"
        else:
            implied_volatility = round(iv, 4)
            iv_premium_ratio = round(iv / vol, 2) if vol else None
            iv_crush_risk = bool(historical_volatility and iv > 1.5 * historical_volatility)
            ratio = iv / vol if vol else 1.0
            if ratio <= 1.2:
                iv_bubble = "NONE"
            elif ratio <= 1.5:
                iv_bubble = "ELEVATED"
            elif ratio <= 2.0:
                iv_bubble = "HIGH"
            else:
                iv_bubble = "EXTREME"

        if iv is not None and iv == iv and iv > 0:
            greeks = self._bs(stock_price, strike_price, T, r, iv, option_type)
            greeks_vol = "IV"
        else:
            greeks_vol = "HV"

        delta = greeks["delta"]
        d2 = greeks["d2"]

        omega = (delta * stock_price / option_price) if option_price > 0 else 0.0
        theta_burn_pct = (abs(greeks["theta"]) / option_price * 100.0) if option_price > 0 else 0.0

        distance_pct = (round(((strike_price - stock_price) / stock_price) * 100, 2)
                        if stock_price > 0 else 0)

        ad = abs(delta)
        if 0.45 <= ad <= 0.70:
            _delta_score = 1.0
        elif (0.30 <= ad < 0.45) or (0.70 < ad <= 0.80):
            _delta_score = 0.5
        else:
            _delta_score = 0.0

        _liq = min(volume / 100000.0, 1.0)

        _iv_pen = 0.0
        if iv_premium_ratio is not None and iv_premium_ratio > 1.2:
            _iv_pen = min(0.6, (iv_premium_ratio - 1.2) * 0.5)

        _theta_pen = min(0.4, theta_burn_pct / 4.0)

        risk_reward_ratio = round(_delta_score * 2.0 + _liq - _iv_pen - _theta_pen, 3)

        if T > 0:
            pop = (_norm_cdf(-d2) if option_type == "PUT" else _norm_cdf(d2)) * 100
            probability_of_profit = round(max(0.0, min(100.0, pop)), 1)
        else:
            probability_of_profit = 100.0 if intrinsic > 0 else 0.0

        return {
            "stock_price": stock_price, "strike_price": strike_price,
            "option_price": option_price, "days_to_expire": days_to_expire,
            "option_type": option_type, "volume": volume,
            "intrinsic": round(intrinsic, 2), "time_value": round(time_value, 2),
            "leverage": round(leverage, 2),
            "omega": round(omega, 2),
            "theta_burn_pct": round(theta_burn_pct, 2),
            "break_even": round(break_even, 2),
            "fair_value": round(fair_value, 2), "delta": round(delta, 3),
            "gamma": round(greeks["gamma"], 5), "theta": round(greeks["theta"], 3),
            "vega": round(greeks["vega"], 3), "valuation": valuation,
            "data_quality": data_quality, "warnings": warnings,
            "volatility_used": volatility_used, "implied_volatility": implied_volatility,
            "greeks_vol": greeks_vol,
            "iv_premium_ratio": iv_premium_ratio, "iv_crush_risk": iv_crush_risk,
            "iv_bubble": iv_bubble,
            "distance_pct": distance_pct, "risk_reward_ratio": risk_reward_ratio,
            "probability_of_profit": probability_of_profit,
        }


if __name__ == "__main__":
    engine = OptionEngine()
    r = engine.analyze(52097, 50000, 9300, 67, "CALL", 96207, 0.527)
    print("=" * 55)
    print("موتور اپشن (یونانی‌ها با IV)")
    print("=" * 55)
    for k, v in r.items():
        print(f"  {k:<22}: {v}")
    print("=" * 55)