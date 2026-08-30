# -*- coding: utf-8 -*-
"""
FIBONACCI RETRACEMENT - سطوح حمایت/مقاومت فیبوناچی (نسخه‌ی جهت‌دار)

برخلاف نسخه‌ی قبلی که بازه‌ی سقف/کف رو بدون توجه به جهت روند به‌عنوان
یه رنج ثابت در نظر می‌گرفت، این نسخه اول تشخیص می‌ده روند صعودیه یا نزولی
(بر اساس اینکه کدوم اکسترمم -سقف یا کف- جدیدتره)، و بعد سطوح فیبوناچی رو
از اکسترمم جدیدتر به سمت قدیمی‌تر اندازه‌گیری می‌کنه — دقیقاً طبق تفسیر
استاندارد «ریتریسمنت در جهت روند»:

  - روند صعودی (کف قبل از سقف اتفاق افتاده): ریتریسمنت از سقف به سمت کف
    اندازه‌گیری می‌شه. نزدیک شدن قیمت به سطح ۰.۶۱۸ (Golden Pocket) یعنی
    یه پولبک سالم روی روند صعودی -> ناحیه‌ی خرید کلاسیک (BULLISH).
  - روند نزولی (سقف قبل از کف اتفاق افتاده): ریتریسمنت از کف به سمت سقف
    اندازه‌گیری می‌شه. نزدیک شدن قیمت به سطح ۰.۶۱۸ یعنی یه ریباند روی
    روند نزولی -> ناحیه‌ی فروش کلاسیک (BEARISH).
"""
import pandas as pd


class Fibonacci:

    def __init__(self, df, lookback=50):
        self.df = df
        self.lookback = lookback
        self.strength = 50.0
        self.levels = {}
        self.current_zone = "MIDDLE"
        self.trend = "UNKNOWN"
        self.nearest_support = None
        self.nearest_resistance = None
        self.details = {}

    def _find_swing_points(self, prices):
        """سقف/کف نوسانی + تشخیص اینکه کدوم جدیدتره (برای تعیین جهت روند)."""
        vals = prices.values
        n = len(vals)
        if n < 10:
            return None, None, None

        window = min(10, n // 3)
        highs = prices.rolling(window=window, center=True).max().values
        lows = prices.rolling(window=window, center=True).min().values

        swing_high = swing_high_idx = None
        swing_low = swing_low_idx = None

        start_idx = max(0, n - self.lookback)
        for i in range(n - 1, start_idx, -1):
            if pd.notna(highs[i]) and vals[i] == highs[i]:
                if swing_high is None:
                    swing_high = float(vals[i])
                    swing_high_idx = i
            if pd.notna(lows[i]) and vals[i] == lows[i]:
                if swing_low is None:
                    swing_low = float(vals[i])
                    swing_low_idx = i
            if swing_high is not None and swing_low is not None:
                break

        tail_start = max(0, n - self.lookback)
        tail = vals[tail_start:]
        if swing_high is None:
            swing_high = float(tail.max())
            swing_high_idx = tail_start + int(tail.argmax())
        if swing_low is None:
            swing_low = float(tail.min())
            swing_low_idx = tail_start + int(tail.argmin())

        # روند صعودی یعنی کف قدیمی‌تره و سقف جدیدتر (آخرین حرکت بزرگ: کف -> سقف)
        trend_up = swing_low_idx <= swing_high_idx

        return swing_high, swing_low, trend_up

    def calculate(self):
        """محاسبه سطوح فیبوناچی (جهت‌دار) و تولید سیگنال"""
        try:
            prices = self.df["last_price"].astype(float)

            if len(prices) < 20:
                self.strength = 50.0
                return "NEUTRAL"

            swing_high, swing_low, trend_up = self._find_swing_points(prices)

            if swing_high is None or swing_low is None:
                self.strength = 50.0
                return "NEUTRAL"

            # اصلاح: اگه سقف و کف خیلی نزدیک بودن، بازه رو بزرگ‌تر کن
            if swing_high <= swing_low * 1.001:
                sma20 = float(prices.tail(20).mean())
                swing_high = max(swing_high, sma20 * 1.05)
                swing_low = min(swing_low, sma20 * 0.95)
                trend_up = True  # حالت پیش‌فرض وقتی بازه به‌اندازه‌ی کافی مشخص نیست

            current_price = float(prices.iloc[-1])
            price_range = swing_high - swing_low

            if price_range <= 0:
                self.strength = 50.0
                return "NEUTRAL"

            # سطوح فیبوناچی — جهت اندازه‌گیری بر اساس روند:
            #  صعودی: 0%=سقف (جدیدترین اکسترمم) ... 100%=کف
            #  نزولی: 0%=کف (جدیدترین اکسترمم) ... 100%=سقف
            ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
            fib_levels = {}
            for r in ratios:
                if trend_up:
                    fib_levels[str(r)] = swing_high - r * price_range
                else:
                    fib_levels[str(r)] = swing_low + r * price_range

            self.levels = fib_levels
            self.trend = "UP" if trend_up else "DOWN"

            golden = fib_levels["0.618"]
            shallow = fib_levels["0.382"]
            deep = fib_levels["0.786"]

            # نزدیک‌ترین حمایت و مقاومت
            supports = [v for v in fib_levels.values() if v < current_price * 0.998]
            resistances = [v for v in fib_levels.values() if v > current_price * 1.002]
            self.nearest_support = max(supports) if supports else swing_low
            self.nearest_resistance = min(resistances) if resistances else swing_high

            if abs(self.nearest_support - self.nearest_resistance) < current_price * 0.001:
                self.nearest_support = min(golden, shallow)
                self.nearest_resistance = max(golden, shallow)

            dist_to_support = ((current_price - self.nearest_support) / current_price * 100
                              if current_price > 0 else 0)
            dist_to_resistance = ((self.nearest_resistance - current_price) / current_price * 100
                                 if current_price > 0 else 0)

            # تعیین ناحیه‌ی قیمت — بر اساس جهت روند
            if trend_up:
                if current_price >= swing_high * 0.998:
                    self.current_zone = "BREAKOUT_HIGH"       # شکست سقف اخیر در روند صعودی
                elif current_price <= swing_low * 1.002:
                    self.current_zone = "TREND_BROKEN_LOW"    # روند صعودی نقض شد
                elif deep * 0.998 <= current_price <= golden * 1.002:
                    self.current_zone = "GOLDEN_POCKET"       # پولبک سالم به سمت کف
                elif current_price <= shallow * 1.002:
                    self.current_zone = "SHALLOW_PULLBACK"    # پولبک خیلی کم‌عمق
                else:
                    self.current_zone = "MID_RETRACE"
            else:
                if current_price <= swing_low * 1.002:
                    self.current_zone = "BREAKDOWN_LOW"       # شکست کف اخیر در روند نزولی
                elif current_price >= swing_high * 0.998:
                    self.current_zone = "TREND_BROKEN_HIGH"   # روند نزولی نقض شد
                elif golden * 0.998 <= current_price <= deep * 1.002:
                    self.current_zone = "GOLDEN_POCKET"       # ریباند به سمت سقف
                elif current_price >= shallow * 0.998:
                    self.current_zone = "SHALLOW_PULLBACK"
                else:
                    self.current_zone = "MID_RETRACE"

            # تولید سیگنال بر اساس ناحیه و جهت روند
            if trend_up:
                if self.current_zone == "BREAKOUT_HIGH":
                    signal, s = "BULLISH", 75      # شکست سقف در روند صعودی -> ادامه‌ی صعود
                elif self.current_zone == "TREND_BROKEN_LOW":
                    signal, s = "BEARISH", 20      # کف روند شکسته شده -> روند نقض شد
                elif self.current_zone == "GOLDEN_POCKET":
                    signal, s = "BULLISH", 80      # پولبک سالم -> نقطه‌ی ورود کلاسیک
                elif self.current_zone == "SHALLOW_PULLBACK":
                    signal, s = "BULLISH", 65      # روند خیلی قویه، کم پولبک کرده
                else:
                    signal, s = "NEUTRAL", 55
            else:
                if self.current_zone == "BREAKDOWN_LOW":
                    signal, s = "BEARISH", 25      # شکست کف در روند نزولی -> ادامه‌ی نزول
                elif self.current_zone == "TREND_BROKEN_HIGH":
                    signal, s = "BULLISH", 80      # سقف روند شکسته شده -> روند نقض شد
                elif self.current_zone == "GOLDEN_POCKET":
                    signal, s = "BEARISH", 20      # ریباند به سقف -> ناحیه‌ی فروش کلاسیک
                elif self.current_zone == "SHALLOW_PULLBACK":
                    signal, s = "BEARISH", 35
                else:
                    signal, s = "NEUTRAL", 45

            sma20 = float(prices.tail(20).mean())
            if current_price > sma20:
                s += 5
            else:
                s -= 5

            self.strength = max(0, min(100, s))

            self.details = {
                "trend": self.trend,
                "swing_high": round(swing_high, 2),
                "swing_low": round(swing_low, 2),
                "current_price": round(current_price, 2),
                "zone": self.current_zone,
                "nearest_support": round(self.nearest_support, 2),
                "nearest_resistance": round(self.nearest_resistance, 2),
                "dist_to_support": round(dist_to_support, 2),
                "dist_to_resistance": round(dist_to_resistance, 2),
                "levels": {k: round(v, 2) for k, v in fib_levels.items()},
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

    fib = Fibonacci(df)
    signal = fib.calculate()

    print("=" * 55)
    print("FIBONACCI RETRACEMENT (جهت‌دار)")
    print("=" * 55)
    print(f"روند: {fib.trend}")
    print(f"سیگنال: {signal}")
    print(f"قدرت: {fib.strength}/100")
    print(f"موقعیت: {fib.current_zone}")
    print(f"حمایت نزدیک: {fib.nearest_support}")
    print(f"مقاومت نزدیک: {fib.nearest_resistance}")
    print("-" * 55)
    for k, v in fib.details.get("levels", {}).items():
        print(f"  {k}: {v}")
    print("=" * 55)