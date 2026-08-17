# -*- coding: utf-8 -*-
"""
VWAP روزانه تقریبی - اصلاح شده
"""

import pandas as pd


class VWAP:

    def __init__(self, df, period=20):
        self.df = df.copy()
        self.period = period
        self.strength = 50

        self.distance_pct = 0.0
        self.slope = "FLAT"
        self.band_position = "ON_VWAP"
        self.chase_warning = False
        self.reclaim = "NONE"
        self.details = {}

    def _prepare(self):
        close_col = None
        for col in ("close", "last_price", "price", "adj_close"):
            if col in self.df.columns:
                close_col = col
                break

        if close_col is None:
            raise ValueError("ستون close پیدا نشد")

        high_col = "high" if "high" in self.df.columns else close_col
        low_col = "low" if "low" in self.df.columns else close_col

        close = pd.to_numeric(self.df[close_col], errors="coerce")
        high = pd.to_numeric(self.df[high_col], errors="coerce")
        low = pd.to_numeric(self.df[low_col], errors="coerce")

        if "volume" in self.df.columns:
            volume = pd.to_numeric(self.df["volume"], errors="coerce").fillna(1.0)
        else:
            volume = pd.Series([1.0] * len(close), index=close.index)

        typical = (high + low + close) / 3.0

        return close, high, low, volume, typical

    def calculate(self):
        try:
            close, high, low, volume, typical = self._prepare()
        except Exception:
            return "NEUTRAL"

        if len(close) < self.period:
            return "NEUTRAL"

        pv = typical * volume
        rolling_pv = pv.rolling(self.period).sum()
        rolling_vol = volume.rolling(self.period).sum()

        # جلوگیری از تقسیم بر صفر
        vwap = (rolling_pv / rolling_vol.replace(0, 1e-9)).ffill()

        last_close = close.iloc[-1]
        last_vwap = vwap.iloc[-1]

        if pd.isna(last_close) or pd.isna(last_vwap) or float(last_vwap) <= 0:
            return "NEUTRAL"

        last_close = float(last_close)
        last_vwap = float(last_vwap)

        distance_pct = (last_close - last_vwap) / last_vwap * 100.0
        self.distance_pct = round(distance_pct, 2)

        # محاسبه std با dropna
        diff = (close - vwap).dropna()
        
        if len(diff) < self.period:
            std = last_vwap * 0.01
        else:
            std_val = diff.rolling(self.period).std().iloc[-1]
            if pd.isna(std_val) or std_val <= 0:
                std = last_vwap * 0.01
            else:
                std = float(std_val)

        u1 = last_vwap + std
        u2 = last_vwap + 2 * std
        l1 = last_vwap - std
        l2 = last_vwap - 2 * std

        if last_close >= u2:
            bp = "EXTREME_HIGH"
        elif last_close >= u1:
            bp = "HIGH"
        elif last_close <= l2:
            bp = "EXTREME_LOW"
        elif last_close <= l1:
            bp = "LOW"
        else:
            bp = "ON_VWAP"

        self.band_position = bp
        self.chase_warning = bp in ("EXTREME_HIGH", "EXTREME_LOW")

        # شیب
        if len(vwap) >= 6:
            v6 = vwap.iloc[-6]
            if pd.notna(v6) and float(v6) > 0:
                chg = (last_vwap - float(v6)) / float(v6) * 100.0
                if chg > 0.2:
                    self.slope = "RISING"
                elif chg < -0.2:
                    self.slope = "FALLING"
                else:
                    self.slope = "FLAT"

        # reclaim
        if len(vwap) >= 4:
            recent_close = close.iloc[-4:-1]
            recent_vwap = vwap.iloc[-4:-1]

            # حذف NA
            mask = recent_close.notna() & recent_vwap.notna()
            rc = recent_close[mask]
            rv = recent_vwap[mask]

            if len(rc) >= 2:
                below_before = bool((rc < rv).all())
                above_before = bool((rc > rv).all())

                if below_before and last_close > last_vwap:
                    self.reclaim = "BULLISH_RECLAIM"
                elif above_before and last_close < last_vwap:
                    self.reclaim = "BEARISH_BREAK"

        # امتیاز
        s = 50

        if last_close > last_vwap:
            s += 15
            if bp == "ON_VWAP":
                s += 5
            elif bp == "HIGH":
                s += 2
            elif bp == "EXTREME_HIGH":
                s -= 8
        elif last_close < last_vwap:
            s -= 15
            if bp == "LOW":
                s -= 2
            elif bp == "EXTREME_LOW":
                s += 8

        if self.slope == "RISING":
            s += 8
        elif self.slope == "FALLING":
            s -= 8

        if self.reclaim == "BULLISH_RECLAIM":
            s += 10
        elif self.reclaim == "BEARISH_BREAK":
            s -= 10

        self.strength = max(0, min(100, int(round(s))))

        self.details = {
            "close": round(last_close, 2),
            "vwap_20": round(last_vwap, 2),
            "distance_pct": self.distance_pct,
            "slope": self.slope,
            "band_position": bp,
            "std": round(float(std), 2),
            "upper_band_1": round(float(u1), 2),
            "upper_band_2": round(float(u2), 2),
            "lower_band_1": round(float(l1), 2),
            "lower_band_2": round(float(l2), 2),
            "chase_warning": self.chase_warning,
            "reclaim": self.reclaim,
        }

        if last_close > last_vwap:
            return "ABOVE"
        if last_close < last_vwap:
            return "BELOW"
        return "ON"


if __name__ == "__main__":
    import sqlite3
    import config

    conn = sqlite3.connect(config.DATABASE_NAME)
    df = pd.read_sql("SELECT date, high, low, close, volume FROM prices ORDER BY date", conn)
    conn.close()

    v = VWAP(df)
    sig = v.calculate()

    print("=" * 55)
    print("VWAP Daily")
    print("=" * 55)
    print("Signal:", sig)
    print("Strength:", v.strength)
    for k, val in v.details.items():
        print(k, ":", val)