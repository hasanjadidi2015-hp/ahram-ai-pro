# -*- coding: utf-8 -*-
"""
Market Regime - نسخه روزانه
تشخیص وضعیت روند کلی سهم.
خروجی:
{
    "trend": "BULL" / "BEAR" / "SIDEWAYS",
    "strength": "STRONG" / "MEDIUM" / "WEAK",
    "score": ...
}
"""

import pandas as pd


class MarketRegime:

    def __init__(self, df):
        self.df = df.copy()
        self.details = {}

    def _get_price(self):
        for col in ("close", "last_price", "price", "adj_close"):
            if col in self.df.columns:
                return pd.to_numeric(self.df[col], errors="coerce")
        raise ValueError("ستون قیمت پیدا نشد")

    def analyze(self):
        try:
            price = self._get_price()
        except Exception:
            return {
                "trend": "SIDEWAYS",
                "strength": "WEAK",
                "score": 0,
                "reason": "no price column"
            }

        if len(price) < 60:
            return {
                "trend": "SIDEWAYS",
                "strength": "WEAK",
                "score": 0,
                "reason": "not enough data"
            }

        close = price.dropna()
        if len(close) < 60:
            return {
                "trend": "SIDEWAYS",
                "strength": "WEAK",
                "score": 0,
                "reason": "not enough valid data"
            }

        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()

        last = float(close.iloc[-1])
        last_ma20 = ma20.iloc[-1]
        last_ma50 = ma50.iloc[-1]

        if pd.isna(last_ma20) or pd.isna(last_ma50):
            return {
                "trend": "SIDEWAYS",
                "strength": "WEAK",
                "score": 0,
                "reason": "ma not ready"
            }

        last_ma20 = float(last_ma20)
        last_ma50 = float(last_ma50)

        score = 0

        # موقعیت قیمت نسبت به میانگین‌ها
        if last > last_ma20:
            score += 25
        else:
            score -= 25

        if last > last_ma50:
            score += 25
        else:
            score -= 25

        # ترتیب میانگین‌ها
        if last_ma20 > last_ma50:
            score += 25
        else:
            score -= 25

        # مومنتوم 20 روزه
        p20 = close.iloc[-21]
        if pd.notna(p20) and float(p20) > 0:
            momentum_20 = (last - float(p20)) / float(p20) * 100
        else:
            momentum_20 = 0

        if momentum_20 > 8:
            score += 25
        elif momentum_20 > 3:
            score += 15
        elif momentum_20 < -8:
            score -= 25
        elif momentum_20 < -3:
            score -= 15

        # محدودسازی
        score = max(-100, min(100, score))

        if score >= 50:
            trend = "BULL"
        elif score <= -50:
            trend = "BEAR"
        else:
            trend = "SIDEWAYS"

        abs_score = abs(score)

        if abs_score >= 75:
            strength = "STRONG"
        elif abs_score >= 50:
            strength = "MEDIUM"
        else:
            strength = "WEAK"

        self.details = {
            "price": round(last, 2),
            "ma20": round(last_ma20, 2),
            "ma50": round(last_ma50, 2),
            "momentum_20_pct": round(momentum_20, 2),
            "score": score,
            "trend": trend,
            "strength": strength,
        }

        return {
            "trend": trend,
            "strength": strength,
            "score": score,
            "price": round(last, 2),
            "ma20": round(last_ma20, 2),
            "ma50": round(last_ma50, 2),
            "momentum_20_pct": round(momentum_20, 2),
        }


if __name__ == "__main__":
    import sqlite3
    import config

    conn = sqlite3.connect(config.DATABASE_NAME)
    df = pd.read_sql("SELECT date, close FROM prices ORDER BY date", conn)
    conn.close()

    m = MarketRegime(df)
    result = m.analyze()

    print("=" * 55)
    print("Market Regime Daily")
    print("=" * 55)
    print(result)