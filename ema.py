# -*- coding: utf-8 -*-
class EMA:
    def __init__(self, df):
        self.df = df
        self.strength = 50.0
    def calculate(self):
        try:
            p = self.df["last_price"].astype(float)
            if len(p) < 50:
                self.strength = 50.0
                return "NEUTRAL"
            e20 = float(p.ewm(span=20, adjust=False).mean().iloc[-1])
            e50 = float(p.ewm(span=50, adjust=False).mean().iloc[-1])
            last = float(p.iloc[-1])
            if last > e20 > e50:
                gap = (last - e50) / e50 * 100
                self.strength = min(100.0, 70.0 + gap * 3.0)
                return "BULLISH"
            if last < e20 < e50:
                gap = (e50 - last) / e50 * 100
                self.strength = max(0.0, 30.0 - gap * 3.0)
                return "BEARISH"
            self.strength = 50.0
            return "NEUTRAL"
        except Exception:
            self.strength = 50.0
            return "NEUTRAL"