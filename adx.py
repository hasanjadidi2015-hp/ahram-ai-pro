# -*- coding: utf-8 -*-
import numpy as np
class ADX:
    def __init__(self, df):
        self.df = df
        self.strength = 50.0
        self.adx_value = 0.0
    def calculate(self):
        try:
            close = self.df["last_price"].astype(float)
            if len(close) < 28:
                self.strength = 50.0
                return "NEUTRAL"
            up = close.diff()
            plus_dm = up.where((up > 0) & (up > -up.shift()), 0.0)
            minus_dm = (-up).where((-up > 0) & (-up > up.shift()), 0.0)
            tr = close.diff().abs().replace(0, np.nan)
            atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
            plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr
            minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
            adx = dx.ewm(alpha=1 / 14, adjust=False).mean()
            av = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0
            self.adx_value = av
            pdi = float(plus_di.iloc[-1]) if not np.isnan(plus_di.iloc[-1]) else 0.0
            mdi = float(minus_di.iloc[-1]) if not np.isnan(minus_di.iloc[-1]) else 0.0
            if pdi > mdi:
                self.strength = min(100.0, 50.0 + min(50.0, av * 1.5))
                return "BULLISH" if av > 20 else "NEUTRAL"
            if mdi > pdi:
                self.strength = max(0.0, 50.0 - min(50.0, av * 1.5))
                return "BEARISH" if av > 20 else "NEUTRAL"
            self.strength = 50.0
            return "NEUTRAL"
        except Exception:
            self.strength = 50.0
            return "NEUTRAL"