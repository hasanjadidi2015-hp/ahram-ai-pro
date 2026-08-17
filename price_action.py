# -*- coding: utf-8 -*-
"""
Price Action - نسخه روزانه
استفاده از high/low/close/volume واقعی.
"""

import pandas as pd


class PriceAction:

    def __init__(self, df, period=20):
        self.df = df.copy()
        self.period = period
        self.strength = 50

        self.new_high = False
        self.new_low = False
        self.volume_ratio = 1.0
        self.volume_confirmed = False
        self.false_breakout = False
        self.trend_structure = "MIXED"
        self.momentum_pct = 0.0
        self.details = {}

    def _cols(self):
        close_col = None
        for col in ("close", "last_price", "price", "adj_close"):
            if col in self.df.columns:
                close_col = col
                break

        if close_col is None:
            raise ValueError("ستون close پیدا نشد")

        high_col = "high" if "high" in self.df.columns else close_col
        low_col = "low" if "low" in self.df.columns else close_col
        volume_col = "volume" if "volume" in self.df.columns else None

        return close_col, high_col, low_col, volume_col

    def analyze(self):
        try:
            close_col, high_col, low_col, volume_col = self._cols()
        except Exception:
            return "NEUTRAL"

        close = pd.to_numeric(self.df[close_col], errors="coerce")
        high = pd.to_numeric(self.df[high_col], errors="coerce")
        low = pd.to_numeric(self.df[low_col], errors="coerce")

        if len(close) < self.period + 2:
            return "NEUTRAL"

        last_close = close.iloc[-1]

        prev_high = high.iloc[:-1].rolling(self.period).max().iloc[-1]
        prev_low = low.iloc[:-1].rolling(self.period).min().iloc[-1]

        if any(pd.isna(x) for x in [last_close, prev_high, prev_low]):
            return "NEUTRAL"

        last_close = float(last_close)
        prev_high = float(prev_high)
        prev_low = float(prev_low)

        self.new_high = last_close > prev_high
        self.new_low = last_close < prev_low

        # حجم
        if volume_col:
            vol = pd.to_numeric(self.df[volume_col], errors="coerce")
            recent_vol = vol.iloc[:-1].tail(self.period)
            avg_vol = float(recent_vol.mean()) if len(recent_vol) else 0
            last_vol = float(vol.iloc[-1]) if pd.notna(vol.iloc[-1]) else 0

            if avg_vol > 0:
                self.volume_ratio = round(last_vol / avg_vol, 2)
                self.volume_confirmed = last_vol >= avg_vol
            else:
                self.volume_confirmed = True
        else:
            self.volume_confirmed = True

        # ساختار روند
        half = max(self.period // 2, 5)
        if len(close) >= 2 * half:
            recent_high = high.tail(half).max()
            recent_low = low.tail(half).min()
            prior_high = high.iloc[-2 * half:-half].max()
            prior_low = low.iloc[-2 * half:-half].min()

            if recent_high > prior_high and recent_low > prior_low:
                self.trend_structure = "HH"
            elif recent_high < prior_high and recent_low < prior_low:
                self.trend_structure = "LL"
            else:
                self.trend_structure = "MIXED"

        lookback = min(5, len(close) - 1)
        if lookback > 0:
            prev_price = close.iloc[-(lookback + 1)]
            if pd.notna(prev_price) and float(prev_price) > 0:
                self.momentum_pct = round((last_close - float(prev_price)) / float(prev_price) * 100.0, 2)

        if self.new_high:
            signal = "BREAKOUT"
            self.false_breakout = not self.volume_confirmed
        elif self.new_low:
            signal = "BREAKDOWN"
            self.false_breakout = not self.volume_confirmed
        else:
            signal = "NEUTRAL"

        s = 50

        if self.new_high:
            s += 18
        if self.new_low:
            s -= 18

        if self.trend_structure == "HH":
            s += 12
        elif self.trend_structure == "LL":
            s -= 12

        if self.momentum_pct > 1:
            s += 8
        elif self.momentum_pct < -1:
            s -= 8

        if self.new_high and self.volume_confirmed:
            s += 7
        if self.new_low and self.volume_confirmed:
            s -= 7

        if self.false_breakout:
            if self.new_high:
                s -= 12
            elif self.new_low:
                s += 12

        self.strength = max(0, min(100, int(round(s))))

        self.details = {
            "close": round(last_close, 2),
            "prev_high_20": round(prev_high, 2),
            "prev_low_20": round(prev_low, 2),
            "new_high": self.new_high,
            "new_low": self.new_low,
            "volume_ratio": self.volume_ratio,
            "volume_confirmed": self.volume_confirmed,
            "false_breakout": self.false_breakout,
            "trend_structure": self.trend_structure,
            "momentum_pct": self.momentum_pct,
        }

        return signal


if __name__ == "__main__":
    import sqlite3
    import config

    conn = sqlite3.connect(config.DATABASE_NAME)
    df = pd.read_sql("SELECT date, high, low, close, volume FROM prices ORDER BY date", conn)
    conn.close()

    pa = PriceAction(df)
    sig = pa.analyze()

    print("=" * 55)
    print("Price Action Daily")
    print("=" * 55)
    print("Signal:", sig)
    print("Strength:", pa.strength)
    for k, v in pa.details.items():
        print(k, ":", v)