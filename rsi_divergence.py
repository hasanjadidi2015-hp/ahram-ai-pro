# -*- coding: utf-8 -*-
"""
RSI DIVERGENCE - تشخیص واگرایی RSI
واگرایی معمولی: سیگنال برگشت
واگرایی مخفی: سیگنال ادامه روند
"""
import pandas as pd


class RSIDivergence:

    def __init__(self, df, rsi_period=14, lookback=30):
        self.df = df
        self.rsi_period = rsi_period
        self.lookback = lookback
        self.strength = 50.0
        self.divergence_type = None  # BULLISH_REGULAR, BEARISH_REGULAR, BULLISH_HIDDEN, BEARISH_HIDDEN
        self.divergence_strength = 0
        self.details = {}

    def _calculate_rsi(self, prices):
        """محاسبه RSI"""
        delta = prices.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/self.rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/self.rsi_period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 0.0001)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _find_peaks_troughs(self, series, window=5):
        """پیدا کردن قله‌ها و دره‌ها"""
        peaks = []
        troughs = []

        for i in range(window, len(series) - window):
            if pd.isna(series.iloc[i]):
                continue
            # قله: بالاتر از همسایه‌ها
            if all(series.iloc[i] >= series.iloc[j] for j in range(i-window, i+window+1) if j != i and pd.notna(series.iloc[j])):
                peaks.append(i)
            # دره: پایین‌تر از همسایه‌ها
            if all(series.iloc[i] <= series.iloc[j] for j in range(i-window, i+window+1) if j != i and pd.notna(series.iloc[j])):
                troughs.append(i)

        return peaks, troughs

    def calculate(self):
        """تشخیص واگرایی RSI"""
        try:
            prices = self.df["last_price"].astype(float)

            if len(prices) < self.lookback:
                self.strength = 50.0
                return "NEUTRAL"

            # محاسبه RSI
            rsi = self._calculate_rsi(prices)

            # استخراج بخش اخیر
            recent_prices = prices.tail(self.lookback).reset_index(drop=True)
            recent_rsi = rsi.tail(self.lookback).reset_index(drop=True)

            # پیدا کردن قله‌ها و دره‌ها
            price_peaks, price_troughs = self._find_peaks_troughs(recent_prices, window=3)
            rsi_peaks, rsi_troughs = self._find_peaks_troughs(recent_rsi, window=3)

            self.divergence_type = None
            self.divergence_strength = 0

            # === واگرایی معمولی صعودی ===
            # قیمت: دره پایین‌تر، RSI: دره بالاتر
            if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
                p1, p2 = price_troughs[-2], price_troughs[-1]
                r1, r2 = rsi_troughs[-2], rsi_troughs[-1]

                if (recent_prices.iloc[p2] < recent_prices.iloc[p1] and
                    recent_rsi.iloc[r2] > recent_rsi.iloc[r1]):
                    self.divergence_type = "BULLISH_REGULAR"
                    self.divergence_strength = 70
                    # هرچه واگرایی قوی‌تر، امتیاز بیشتر
                    price_diff = abs(recent_prices.iloc[p2] - recent_prices.iloc[p1]) / recent_prices.iloc[p1] * 100
                    rsi_diff = abs(recent_rsi.iloc[r2] - recent_rsi.iloc[r1])
                    if price_diff > 2 and rsi_diff > 5:
                        self.divergence_strength = 85

            # === واگرایی معمولی نزولی ===
            # قیمت: قله بالاتر، RSI: قله پایین‌تر
            if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
                p1, p2 = price_peaks[-2], price_peaks[-1]
                r1, r2 = rsi_peaks[-2], rsi_peaks[-1]

                if (recent_prices.iloc[p2] > recent_prices.iloc[p1] and
                    recent_rsi.iloc[r2] < recent_rsi.iloc[r1]):
                    self.divergence_type = "BEARISH_REGULAR"
                    self.divergence_strength = 30
                    price_diff = abs(recent_prices.iloc[p2] - recent_prices.iloc[p1]) / recent_prices.iloc[p1] * 100
                    rsi_diff = abs(recent_rsi.iloc[r2] - recent_rsi.iloc[r1])
                    if price_diff > 2 and rsi_diff > 5:
                        self.divergence_strength = 15

            # === واگرایی مخفی صعودی ===
            # قیمت: دره بالاتر، RSI: دره پایین‌تر (ادامه صعود)
            if self.divergence_type is None and len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
                p1, p2 = price_troughs[-2], price_troughs[-1]
                r1, r2 = rsi_troughs[-2], rsi_troughs[-1]

                if (recent_prices.iloc[p2] > recent_prices.iloc[p1] and
                    recent_rsi.iloc[r2] < recent_rsi.iloc[r1]):
                    self.divergence_type = "BULLISH_HIDDEN"
                    self.divergence_strength = 65

            # === واگرایی مخفی نزولی ===
            # قیمت: قله پایین‌تر، RSI: قله بالاتر (ادامه نزول)
            if self.divergence_type is None and len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
                p1, p2 = price_peaks[-2], price_peaks[-1]
                r1, r2 = rsi_peaks[-2], rsi_peaks[-1]

                if (recent_prices.iloc[p2] < recent_prices.iloc[p1] and
                    recent_rsi.iloc[r2] > recent_rsi.iloc[r1]):
                    self.divergence_type = "BEARISH_HIDDEN"
                    self.divergence_strength = 35

            # تعیین سیگنال و قدرت
            if self.divergence_type == "BULLISH_REGULAR":
                signal = "BULLISH"
                self.strength = self.divergence_strength
            elif self.divergence_type == "BEARISH_REGULAR":
                signal = "BEARISH"
                self.strength = self.divergence_strength
            elif self.divergence_type == "BULLISH_HIDDEN":
                signal = "BULLISH"
                self.strength = self.divergence_strength
            elif self.divergence_type == "BEARISH_HIDDEN":
                signal = "BEARISH"
                self.strength = self.divergence_strength
            else:
                signal = "NEUTRAL"
                self.strength = 50.0

            current_rsi = float(recent_rsi.iloc[-1]) if pd.notna(recent_rsi.iloc[-1]) else 50

            self.details = {
                "divergence_type": self.divergence_type or "NONE",
                "divergence_strength": self.divergence_strength,
                "current_rsi": round(current_rsi, 2),
                "price_peaks_found": len(price_peaks),
                "price_troughs_found": len(price_troughs),
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

    rd = RSIDivergence(df)
    signal = rd.calculate()

    print("=" * 55)
    print("RSI DIVERGENCE")
    print("=" * 55)
    print(f"سیگنال: {signal}")
    print(f"قدرت: {rd.strength}/100")
    print(f"نوع واگرایی: {rd.divergence_type or 'ندارد'}")
    print(f"RSI فعلی: {rd.details.get('current_rsi')}")
    print("=" * 55)