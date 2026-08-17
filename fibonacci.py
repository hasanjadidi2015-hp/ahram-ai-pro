# -*- coding: utf-8 -*-
"""
FIBONACCI RETRACEMENT - سطوح حمایت/مقاومت فیبوناچی
شناسایی سطوح کلیدی و موقعیت قیمت نسبت به آنها
"""
import pandas as pd


class Fibonacci:

    def __init__(self, df, lookback=50):
        self.df = df
        self.lookback = lookback
        self.strength = 50.0
        self.levels = {}
        self.current_zone = "MIDDLE"
        self.nearest_support = None
        self.nearest_resistance = None
        self.details = {}

    def _find_swing_points(self, prices):
        """پیدا کردن سقف و کف نوسانی"""
        if len(prices) < 10:
            return None, None

        window = min(10, len(prices) // 3)
        highs = prices.rolling(window=window, center=True).max()
        lows = prices.rolling(window=window, center=True).min()

        swing_high = None
        swing_low = None

        for i in range(len(prices) - 1, max(0, len(prices) - self.lookback), -1):
            if pd.notna(highs.iloc[i]) and prices.iloc[i] == highs.iloc[i]:
                if swing_high is None:
                    swing_high = float(prices.iloc[i])
            if pd.notna(lows.iloc[i]) and prices.iloc[i] == lows.iloc[i]:
                if swing_low is None:
                    swing_low = float(prices.iloc[i])
            if swing_high and swing_low:
                break

        if swing_high is None:
            swing_high = float(prices.tail(self.lookback).max())
        if swing_low is None:
            swing_low = float(prices.tail(self.lookback).min())

        return swing_high, swing_low

    def calculate(self):
        """محاسبه سطوح فیبوناچی و تولید سیگنال"""
        try:
            prices = self.df["last_price"].astype(float)

            if len(prices) < 20:
                self.strength = 50.0
                return "NEUTRAL"

            swing_high, swing_low = self._find_swing_points(prices)

            if swing_high is None or swing_low is None:
                self.strength = 50.0
                return "NEUTRAL"

            # اصلاح: اگه سقف و کف خیلی نزدیک بودن، بازه رو بزرگ‌تر کن
            if swing_high <= swing_low * 1.001:
                # از میانگین متحرک برای تعیین بازه استفاده کن
                sma20 = float(prices.tail(20).mean())
                swing_high = max(swing_high, sma20 * 1.05)
                swing_low = min(swing_low, sma20 * 0.95)

            current_price = float(prices.iloc[-1])
            price_range = swing_high - swing_low

            if price_range <= 0:
                self.strength = 50.0
                return "NEUTRAL"

            # سطوح فیبوناچی
            fib_levels = {
                "0.0": swing_low,
                "0.236": swing_low + 0.236 * price_range,
                "0.382": swing_low + 0.382 * price_range,
                "0.5": swing_low + 0.5 * price_range,
                "0.618": swing_low + 0.618 * price_range,
                "0.786": swing_low + 0.786 * price_range,
                "1.0": swing_high,
            }

            self.levels = fib_levels

            # پیدا کردن نزدیک‌ترین حمایت و مقاومت (متفاوت از قیمت فعلی)
            supports = [v for k, v in fib_levels.items() if v < current_price * 0.998]
            resistances = [v for k, v in fib_levels.items() if v > current_price * 1.002]

            self.nearest_support = max(supports) if supports else swing_low
            self.nearest_resistance = min(resistances) if resistances else swing_high

            # اطمینان از اینکه حمایت و مقاومت یکسان نیستن
            if abs(self.nearest_support - self.nearest_resistance) < current_price * 0.001:
                self.nearest_support = fib_levels.get("0.382", swing_low)
                self.nearest_resistance = fib_levels.get("0.618", swing_high)

            # تعیین موقعیت قیمت
            if current_price >= swing_high * 0.998:
                self.current_zone = "ABOVE_HIGH"
            elif current_price <= swing_low * 1.002:
                self.current_zone = "BELOW_LOW"
            elif current_price >= fib_levels["0.618"] * 0.998:
                self.current_zone = "GOLDEN_POCKET"
            elif current_price <= fib_levels["0.382"] * 1.002:
                self.current_zone = "DEEP_SUPPORT"
            elif current_price >= fib_levels["0.5"]:
                self.current_zone = "UPPER_HALF"
            else:
                self.current_zone = "LOWER_HALF"

            # محاسبه فاصله از سطوح کلیدی
            dist_to_support = ((current_price - self.nearest_support) / current_price * 100
                              if current_price > 0 else 0)
            dist_to_resistance = ((self.nearest_resistance - current_price) / current_price * 100
                                 if current_price > 0 else 0)

            # تولید سیگنال
            signal = "NEUTRAL"
            s = 50

            if self.current_zone in ("DEEP_SUPPORT", "BELOW_LOW"):
                signal = "BULLISH"
                s = 70
                if dist_to_support < 2:
                    s = 80
            elif self.current_zone in ("GOLDEN_POCKET", "ABOVE_HIGH"):
                signal = "BEARISH"
                s = 30
                if dist_to_resistance < 2:
                    s = 20
            elif self.current_zone == "LOWER_HALF":
                signal = "BULLISH"
                s = 60
            elif self.current_zone == "UPPER_HALF":
                signal = "BEARISH"
                s = 40

            sma20 = float(prices.tail(20).mean())
            if current_price > sma20:
                s += 5
            else:
                s -= 5

            self.strength = max(0, min(100, s))

            self.details = {
                "swing_high": round(swing_high, 2),
                "swing_low": round(swing_low, 2),
                "current_price": round(current_price, 2),
                "zone": self.current_zone,
                "nearest_support": round(self.nearest_support, 2),
                "nearest_resistance": round(self.nearest_resistance, 2),
                "dist_to_support": round(dist_to_support, 2),
                "dist_to_resistance": round(dist_to_resistance, 2),
                "levels": {k: round(v, 2) for k, v in fib_levels.items()},
            }

            return signal

        except Exception as e:
            self.strength = 50.0
            self.details = {"error": str(e)}
            return "NEUTRAL"


if __name__ == "__main__":
    import sqlite3
    import config

    conn = sqlite3.connect(config.DATABASE_NAME)
    df = pd.read_sql("SELECT last_price FROM prices ORDER BY id", conn)
    conn.close()

    fib = Fibonacci(df)
    signal = fib.calculate()

    print("=" * 55)
    print("FIBONACCI RETRACEMENT")
    print("=" * 55)
    print(f"سیگنال: {signal}")
    print(f"قدرت: {fib.strength}/100")
    print(f"موقعیت: {fib.current_zone}")
    print(f"حمایت نزدیک: {fib.nearest_support}")
    print(f"مقاومت نزدیک: {fib.nearest_resistance}")
    print("-" * 55)
    for k, v in fib.details.get("levels", {}).items():
        print(f"  {k}: {v}")
    print("=" * 55)