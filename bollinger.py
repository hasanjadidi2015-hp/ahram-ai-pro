# -*- coding: utf-8 -*-
"""
Bollinger Bands - نسخه روزانه
بر اساس close واقعی روزانه.
"""

import pandas as pd


class Bollinger:

    def __init__(self, df, period=20, num_std=2):
        self.df = df.copy()
        self.period = period
        self.num_std = num_std
        self.strength = 50
        self.percent_b = 50.0
        self.bandwidth = 0.0
        self.squeeze = False
        self.band_position = "MIDDLE"
        self.expanding = False
        self.reversal_risk = False
        self.details = {}

    def _get_price(self):
        for col in ("close", "last_price", "price", "adj_close"):
            if col in self.df.columns:
                return pd.to_numeric(self.df[col], errors="coerce")
        raise ValueError("ستون قیمت پیدا نشد")

    def calculate(self):
        try:
            price = self._get_price()
        except Exception:
            return "NEUTRAL"

        if len(price) < self.period:
            return "NEUTRAL"

        sma = price.rolling(self.period).mean()
        std = price.rolling(self.period).std()

        upper = sma + self.num_std * std
        lower = sma - self.num_std * std

        last_price = price.iloc[-1]
        last_sma = sma.iloc[-1]
        last_upper = upper.iloc[-1]
        last_lower = lower.iloc[-1]

        if any(pd.isna(x) for x in [last_price, last_sma, last_upper, last_lower]):
            return "NEUTRAL"

        last_price = float(last_price)
        last_sma = float(last_sma)
        last_upper = float(last_upper)
        last_lower = float(last_lower)

        if last_sma <= 0:
            return "NEUTRAL"

        band_width_abs = last_upper - last_lower
        if band_width_abs <= 0:
            return "NEUTRAL"

        percent_b = (last_price - last_lower) / band_width_abs * 100.0
        bandwidth = band_width_abs / last_sma * 100.0

        self.percent_b = round(percent_b, 2)
        self.bandwidth = round(bandwidth, 2)

        bw_series = ((upper - lower) / sma * 100.0).dropna()

        if len(bw_series) >= 6:
            prev_bw = float(bw_series.iloc[-6])
            self.expanding = bandwidth > prev_bw

        if len(bw_series) >= 20:
            threshold = float(bw_series.tail(50).quantile(0.2))
            self.squeeze = bandwidth <= threshold

        if last_price > last_upper:
            bp = "ABOVE_UPPER"
        elif last_price > last_sma:
            bp = "UPPER_HALF"
        elif last_price < last_lower:
            bp = "BELOW_LOWER"
        else:
            bp = "LOWER_HALF"

        self.band_position = bp

        lookback = max(self.period // 2, 8)
        trend_up = False
        trend_down = False

        if len(sma) >= lookback + 1 and pd.notna(sma.iloc[-(lookback + 1)]):
            sma_change = last_sma - float(sma.iloc[-(lookback + 1)])
            trend_up = sma_change > 0
            trend_down = sma_change < 0

        breakout_up = last_price > last_upper
        breakout_down = last_price < last_lower

        if breakout_up and trend_up:
            signal = "BULLISH"
        elif breakout_down and trend_down:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        self.reversal_risk = (breakout_up and not trend_up) or (breakout_down and not trend_down)

        s = 50

        if last_price > last_sma:
            s += 10
        elif last_price < last_sma:
            s -= 10

        if breakout_up:
            s += 15 if trend_up else -8
        elif breakout_down:
            s -= 15 if trend_down else -8

        if trend_up:
            s += 5
        elif trend_down:
            s -= 5

        if self.squeeze and self.expanding:
            if trend_up:
                s += 5
            elif trend_down:
                s -= 5

        self.strength = max(0, min(100, int(round(s))))

        self.details = {
            "price": round(last_price, 2),
            "middle_sma": round(last_sma, 2),
            "upper_band": round(last_upper, 2),
            "lower_band": round(last_lower, 2),
            "percent_b": self.percent_b,
            "bandwidth": self.bandwidth,
            "expanding": self.expanding,
            "sma_rising": trend_up,
            "sma_falling": trend_down,
            "squeeze": self.squeeze,
            "band_position": bp,
            "reversal_risk": self.reversal_risk,
        }

        return signal


if __name__ == "__main__":
    import sqlite3
    import config

    conn = sqlite3.connect(config.DATABASE_NAME)
    df = pd.read_sql("SELECT date, close FROM prices ORDER BY date", conn)
    conn.close()

    b = Bollinger(df)
    sig = b.calculate()

    print("=" * 55)
    print("Bollinger Daily")
    print("=" * 55)
    print("Signal:", sig)
    print("Strength:", b.strength)
    for k, v in b.details.items():
        print(k, ":", v)