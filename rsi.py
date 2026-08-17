# -*- coding: utf-8 -*-
"""
RSI - سازگار با دیتای روزانه
از close استفاده می‌کند، اگر نبود از last_price یا price.
"""


class RSI:

    def __init__(self, df, period=14):
        self.df = df
        self.period = period

    def _get_price(self):
        for col in ("close", "last_price", "price", "adj_close"):
            if col in self.df.columns:
                return self.df[col]
        raise ValueError("هیچ ستون قیمتی مناسب برای RSI پیدا نشد")

    def calculate(self):
        try:
            price = self._get_price().astype(float)
        except Exception:
            return None

        if len(price) < self.period + 1:
            return None

        delta = price.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        # Wilder RSI
        avg_gain = gain.ewm(alpha=1 / self.period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / self.period, adjust=False).mean()

        last_loss = avg_loss.iloc[-1]
        last_gain = avg_gain.iloc[-1]

        if last_loss is None or last_loss != last_loss:
            return None

        if last_loss == 0:
            if last_gain == 0:
                return 50.0
            return 100.0

        rs = last_gain / last_loss
        rsi = 100 - (100 / (1 + rs))

        if rsi != rsi:
            return None

        return float(round(rsi, 2))


if __name__ == "__main__":
    import sqlite3
    import pandas as pd
    import config

    conn = sqlite3.connect(config.DATABASE_NAME)
    df = pd.read_sql("SELECT date, close FROM prices ORDER BY date", conn)
    conn.close()

    r = RSI(df)
    print("RSI:", r.calculate())