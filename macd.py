# -*- coding: utf-8 -*-
class MACD:
    def __init__(self, df):
        self.df = df
        self.strength = 50.0
    def calculate(self):
        try:
            p = self.df["last_price"].astype(float)
            if len(p) < 35:
                self.strength = 50.0
                return "NEUTRAL"
            ema12 = p.ewm(span=12, adjust=False).mean()
            ema26 = p.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal = macd_line.ewm(span=9, adjust=False).mean()
            hist = float((macd_line - signal).iloc[-1])
            last = float(p.iloc[-1])
            hn = (hist / last * 100) if last else 0.0
            if hist > 0:
                self.strength = min(100.0, 65.0 + hn * 5.0)
                return "BULLISH"
            if hist < 0:
                self.strength = max(0.0, 35.0 - abs(hn) * 5.0)
                return "BEARISH"
            self.strength = 50.0
            return "NEUTRAL"
        except Exception:
            self.strength = 50.0
            return "NEUTRAL"