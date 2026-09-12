# -*- coding: utf-8 -*-
class EMA:
    SLOPE_BARS = 3  # تعداد کندل عقب‌تر برای سنجش شیب EMA20 (مثل Slope_Bars تو AFL)
    SLOPE_BONUS = 10.0
    SLOPE_PENALTY = 10.0

    def __init__(self, df):
        self.df = df
        self.strength = 50.0
        self.slope_ok = None  # True/False/None (None یعنی داده کافی برای سنجش شیب نبود)

    def calculate(self):
        try:
            p = self.df["last_price"].astype(float)
            if len(p) < 50:
                self.strength = 50.0
                self.slope_ok = None
                return "NEUTRAL"
            e20_series = p.ewm(span=20, adjust=False).mean()
            e50 = float(p.ewm(span=50, adjust=False).mean().iloc[-1])
            e20 = float(e20_series.iloc[-1])
            last = float(p.iloc[-1])

            # شیب EMA20: آیا EMA20 الان از EMA20 چند کندل قبل بالاتر/پایین‌تره؟
            # اگه داده‌ی کافی برای نگاه به عقب نبود، شیب رو نامشخص (None) می‌ذاریم
            # -- نه اینکه به‌اشتباه فرض کنیم شیب "خنثی" یا "تأییدشده" بوده.
            if len(e20_series) > self.SLOPE_BARS:
                e20_prev = float(e20_series.iloc[-1 - self.SLOPE_BARS])
            else:
                e20_prev = None

            if last > e20 > e50:
                gap = (last - e50) / e50 * 100
                self.strength = min(100.0, 70.0 + gap * 3.0)
                if e20_prev is not None:
                    self.slope_ok = e20 > e20_prev
                    self.strength = min(100.0, self.strength + self.SLOPE_BONUS) if self.slope_ok \
                        else max(0.0, self.strength - self.SLOPE_PENALTY)
                else:
                    self.slope_ok = None
                return "BULLISH"

            if last < e20 < e50:
                gap = (e50 - last) / e50 * 100
                self.strength = max(0.0, 30.0 - gap * 3.0)
                if e20_prev is not None:
                    self.slope_ok = e20 < e20_prev
                    self.strength = max(0.0, self.strength - self.SLOPE_BONUS) if self.slope_ok \
                        else min(100.0, self.strength + self.SLOPE_PENALTY)
                else:
                    self.slope_ok = None
                return "BEARISH"

            self.strength = 50.0
            self.slope_ok = None
            return "NEUTRAL"
        except Exception:
            self.strength = 50.0
            self.slope_ok = None
            return "NEUTRAL"