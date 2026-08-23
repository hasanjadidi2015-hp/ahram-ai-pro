# -*- coding: utf-8 -*-
"""
VOLUME ANALYSIS - تحلیل حجم معاملات
استراتژی مووینگ اورج حجم + نسبت Put/Call
"""
import sqlite3
from datetime import datetime

import config


class VolumeAnalysis:
    """تحلیل حجم معاملات با مووینگ اورج"""
    
    def __init__(self, db_name=None):
        self.db = db_name or config.DATABASE_NAME
        self.strength = 50.0
        self.signal = "NEUTRAL"
        self.details = {}
    
    def _get_volume_data(self, days=50):
        """دریافت دیتای حجم از دیتابیس"""
        try:
            conn = sqlite3.connect(self.db)
            cur = conn.cursor()
            cur.execute("""
                SELECT time, volume FROM prices 
                WHERE volume > 0 
                ORDER BY id DESC LIMIT ?
            """, (days,))
            data = cur.fetchall()
            conn.close()
            return [{"date": r[0], "volume": float(r[1])} for r in reversed(data)]
        except Exception:
            return []
    
    def _calc_sma(self, data, period):
        """محاسبه SMA حجم"""
        if len(data) < period:
            return data[-1]["volume"] if data else 0
        return sum(d["volume"] for d in data[-period:]) / period
    
    def calculate(self):
        """محاسبه سیگنال حجم"""
        data = self._get_volume_data()
        
        if len(data) < 30:
            self.signal = "NEUTRAL"
            self.strength = 50.0
            return self.signal
        
        # محاسبه مووینگ اورج‌ها
        vol_5 = self._calc_sma(data, 5)
        vol_10 = self._calc_sma(data, 10)
        vol_30 = self._calc_sma(data, 30)
        
        current_vol = data[-1]["volume"]
        prev_vol_5 = self._calc_sma(data[:-1], 5)
        prev_vol_10 = self._calc_sma(data[:-1], 10)
        
        # تشخیص کراس
        cross_up = vol_5 > vol_10 and prev_vol_5 <= prev_vol_10
        cross_down = vol_5 < vol_10 and prev_vol_5 >= prev_vol_10
        
        # روند حجم
        vol_trend = "NEUTRAL"
        if vol_5 > vol_10 > vol_30:
            vol_trend = "INCREASING"  # حجم در حال افزایش
        elif vol_5 < vol_10 < vol_30:
            vol_trend = "DECREASING"  # حجم در حال کاهش
        
        # نسبت حجم فعلی به میانگین
        vol_ratio = current_vol / vol_30 if vol_30 > 0 else 1.0
        
        # تولید سیگنال
        signal = "NEUTRAL"
        strength = 50.0
        
        if cross_up:
            signal = "BUY"
            strength = 70.0
        elif cross_down:
            signal = "SELL"
            strength = 30.0
        elif vol_trend == "INCREASING" and vol_ratio > 1.5:
            signal = "BUY"
            strength = 65.0
        elif vol_trend == "DECREASING" and vol_ratio < 0.5:
            signal = "SELL"
            strength = 35.0
        
        self.signal = signal
        self.strength = strength
        self.details = {
            "vol_5": round(vol_5),
            "vol_10": round(vol_10),
            "vol_30": round(vol_30),
            "current_vol": round(current_vol),
            "vol_ratio": round(vol_ratio, 2),
            "vol_trend": vol_trend,
            "cross_up": cross_up,
            "cross_down": cross_down,
        }
        
        return signal
    
    def print_report(self):
        """چاپ گزارش"""
        print("=" * 50)
        print("📊 تحلیل حجم معاملات")
        print("=" * 50)
        print(f"  سیگنال: {self.signal}")
        print(f"  قدرت: {self.strength}/100")
        print(f"  MA5: {self.details.get('vol_5', 0):,.0f}")
        print(f"  MA10: {self.details.get('vol_10', 0):,.0f}")
        print(f"  MA30: {self.details.get('vol_30', 0):,.0f}")
        print(f"  حجم فعلی: {self.details.get('current_vol', 0):,.0f}")
        print(f"  نسبت: {self.details.get('vol_ratio', 0)}x")
        print(f"  روند: {self.details.get('vol_trend', 'N/A')}")
        print("=" * 50)


class PutCallRatio:
    """تحلیل نسبت Put به Call"""
    
    def __init__(self, db_name=None):
        self.db = db_name or config.DATABASE_NAME
        self.strength = 50.0
        self.signal = "NEUTRAL"
        self.details = {}
    
    def calculate(self):
        """محاسبه نسبت Put/Call"""
        try:
            conn = sqlite3.connect(self.db)
            cur = conn.cursor()
            
            # آخرین آپشن‌ها
            cur.execute("SELECT MAX(time) FROM options")
            latest = cur.fetchone()[0]
            
            if not latest:
                conn.close()
                self.signal = "NEUTRAL"
                return self.signal
            
            # حجم Put و Call
            cur.execute("""
                SELECT option_type, SUM(volume) 
                FROM options 
                WHERE time = ? AND volume > 0
                GROUP BY option_type
            """, (latest,))
            
            volumes = dict(cur.fetchall())
            conn.close()
            
            call_vol = volumes.get("CALL", 0)
            put_vol = volumes.get("PUT", 0)
            
            if call_vol == 0:
                self.signal = "NEUTRAL"
                self.strength = 50.0
                return self.signal
            
            ratio = put_vol / call_vol
            
            # تفسیر نسبت
            if ratio < 0.7:
                # Call بیشتر = صعودی
                self.signal = "BUY"
                self.strength = 65.0
            elif ratio > 1.3:
                # Put بیشتر = نزولی
                self.signal = "SELL"
                self.strength = 35.0
            else:
                self.signal = "NEUTRAL"
                self.strength = 50.0
            
            self.details = {
                "call_volume": call_vol,
                "put_volume": put_vol,
                "ratio": round(ratio, 2),
            }
            
        except Exception:
            self.signal = "NEUTRAL"
            self.strength = 50.0
        
        return self.signal


class OpenInterestAnalysis:
    """تحلیل موقعیت‌های باز"""
    
    def __init__(self, db_name=None):
        self.db = db_name or config.DATABASE_NAME
        self.strength = 50.0
        self.signal = "NEUTRAL"
        self.details = {}
    
    def calculate(self):
        """محاسبه تغییرات OI -- جدا برای CALL و PUT.

        نکته: موقعیت باز خام فقط می‌گه چند قرارداد بسته نشده؛ نمی‌گه دست
        کیه یا جهتش چیه. رشد OI پوت لزوماً نزولی نیست (می‌تونه هج باشه) و
        رشد OI کال لزوماً صعودی نیست. برای همین به‌جای جمع خام CALL+PUT،
        رشد نسبی هرکدوم رو نسبت به هم می‌سنجیم -- اگه کال بیشتر از پوت رشد
        کرده باشه، بایاس به سمت صعودیه، و برعکس."""
        try:
            conn = sqlite3.connect(self.db)
            cur = conn.cursor()

            cur.execute("SELECT DISTINCT time FROM options ORDER BY time DESC LIMIT 2")
            times = [r[0] for r in cur.fetchall()]

            if len(times) < 2:
                conn.close()
                self.signal = "NEUTRAL"
                return self.signal

            def _oi_by_type(t):
                cur.execute(
                    "SELECT option_type, SUM(open_interest) FROM options WHERE time=? GROUP BY option_type",
                    (t,),
                )
                d = {"CALL": 0.0, "PUT": 0.0}
                for typ, s in cur.fetchall():
                    if typ in d:
                        d[typ] = s or 0.0
                return d

            cur_oi = _oi_by_type(times[0])
            prev_oi = _oi_by_type(times[1])
            conn.close()

            call_change = cur_oi["CALL"] - prev_oi["CALL"]
            put_change = cur_oi["PUT"] - prev_oi["PUT"]
            base = abs(prev_oi["CALL"]) + abs(prev_oi["PUT"])

            if base == 0:
                self.signal = "NEUTRAL"
                return self.signal

            # بایاس خالص: کال بیشتر از پوت رشد کرده (مثبت) یا پوت بیشتر از
            # کال رشد کرده (منفی)
            bias_pct = ((call_change - put_change) / base) * 100

            if bias_pct > 8:
                self.signal = "BUY"
                self.strength = 65.0
            elif bias_pct < -8:
                self.signal = "SELL"
                self.strength = 35.0
            else:
                self.signal = "NEUTRAL"
                self.strength = 50.0

            self.details = {
                "call_oi": cur_oi["CALL"], "put_oi": cur_oi["PUT"],
                "call_oi_change": round(call_change, 1),
                "put_oi_change": round(put_change, 1),
                "bias_pct": round(bias_pct, 2),
            }

        except Exception:
            self.signal = "NEUTRAL"
            self.strength = 50.0

        return self.signal


def analyze_volume(db_name=None):
    """تحلیل کامل حجم"""
    vol = VolumeAnalysis(db_name)
    vol_signal = vol.calculate()
    
    pcr = PutCallRatio(db_name)
    pcr_signal = pcr.calculate()
    
    oi = OpenInterestAnalysis(db_name)
    oi_signal = oi.calculate()
    
    # ترکیب سیگنال‌ها
    signals = [vol_signal, pcr_signal, oi_signal]
    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL")
    
    if buy_count >= 2:
        final = "BUY"
    elif sell_count >= 2:
        final = "SELL"
    else:
        final = "NEUTRAL"
    
    return {
        "volume": vol_signal,
        "put_call": pcr_signal,
        "open_interest": oi_signal,
        "final": final,
        "details": {
            "volume": vol.details,
            "put_call": pcr.details,
            "open_interest": oi.details,
        }
    }


if __name__ == "__main__":
    result = analyze_volume()
    print(f"\n📊 تحلیل حجم:")
    print(f"  حجم: {result['volume']}")
    print(f"  Put/Call: {result['put_call']}")
    print(f"  OI: {result['open_interest']}")
    print(f"  نتیجه: {result['final']}")