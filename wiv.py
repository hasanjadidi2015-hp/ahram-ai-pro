# -*- coding: utf-8 -*-
"""
WIV - Weighted Implied Volatility
میانگین نوسان‌پذیری ضمنی وزنی برای کل قراردادهای یک نماد

محاسبه:
  WIV = Σ(IV_i × W_i) / Σ(W_i)
  
وزن‌دهی بر اساس:
  1. حجم معاملات (Volume)
  2. ارزش باز (Open Interest)
  3. فاصله تا سررسید (Days to Expiry)

کاربرد:
  - تشخیص گرانی/ارزانی آپشن‌ها
  - فیلتر استراتژی (خرید vs فروش)
  - تشخیص IV Crush
"""
import sqlite3
from datetime import datetime

import config
from option_engine import OptionEngine, compute_historical_volatility


class WIVCalculator:
    
    def __init__(self, db_name=None):
        self.db = db_name or config.DATABASE_NAME
        self.engine = OptionEngine()
        self.hv = compute_historical_volatility()
        self.wiv = None
        self.iv_rank = None
        self.iv_percentile = None
        self.contracts_analyzed = 0
        self.details = {}
    
    def _fetch_active_contracts(self):
        """دریافت قراردادهای فعال با حجم و OI مناسب"""
        try:
            conn = sqlite3.connect(self.db)
            cur = conn.cursor()
            
            # آخرین اسنپ‌شات آپشن‌ها
            cur.execute("SELECT MAX(time) FROM options")
            latest = cur.fetchone()[0]
            
            if not latest:
                conn.close()
                return []
            
            # قراردادهای فعال با حداقل حجم و OI
            cur.execute("""
                SELECT 
                    symbol, option_type, stock_price, option_price,
                    strike_price, days_to_expire, volume, open_interest
                FROM options 
                WHERE time = ? 
                    AND option_price > 0 
                    AND volume > 100
                    AND days_to_expire >= 3
                ORDER BY volume DESC
            """, (latest,))
            
            rows = cur.fetchall()
            conn.close()
            return rows
            
        except Exception as e:
            print(f"[WIV] DB Error: {e}")
            return []
    
    def _calculate_iv_for_contract(self, row):
        """محاسبه IV برای یک قرارداد"""
        try:
            symbol, opt_type, stock_price, option_price, strike_price, dte, volume, oi = row
            
            stock_price = float(stock_price)
            option_price = float(option_price)
            strike_price = float(strike_price)
            dte = int(dte or 0)
            volume = float(volume or 0)
            oi = float(oi or 0)
            
            if stock_price <= 0 or option_price <= 0 or strike_price <= 0 or dte <= 0:
                return None
            
            T = dte / 365.0
            r = config.RISK_FREE_RATE
            
            iv = self.engine._implied_vol(option_price, stock_price, strike_price, T, r, opt_type)
            
            if iv is None or iv <= 0 or iv > 5.0:
                return None
            
            return {
                "symbol": symbol,
                "option_type": opt_type,
                "stock_price": stock_price,
                "option_price": option_price,
                "strike_price": strike_price,
                "dte": dte,
                "volume": volume,
                "oi": oi,
                "iv": iv,
                "distance_pct": abs((strike_price - stock_price) / stock_price * 100) if stock_price > 0 else 0
            }
            
        except Exception:
            return None
    
    def calculate(self):
        """محاسبه WIV برای نماد فعلی"""
        contracts = self._fetch_active_contracts()
        
        if not contracts:
            self.wiv = None
            return None
        
        # محاسبه IV برای هر قرارداد
        analyzed = []
        for row in contracts:
            result = self._calculate_iv_for_contract(row)
            if result:
                analyzed.append(result)
        
        if not analyzed:
            self.wiv = None
            return None
        
        self.contracts_analyzed = len(analyzed)
        
        # === وزن‌دهی ===
        # وزن = ترکیب حجم + OI + نزدیکی به ATM
        
        weighted_iv_sum = 0
        total_weight = 0
        
        for c in analyzed:
            iv = c["iv"]
            volume = c["volume"]
            oi = c["oi"]
            distance = c["distance_pct"]
            
            # وزن حجم (هرچه حجم بیشتر، وزن بیشتر)
            volume_weight = volume ** 0.5  # ریشه دوم برای کاهش اثر حجم‌های خیلی بزرگ
            
            # وزن OI
            oi_weight = oi ** 0.3
            
            # وزن نزدیکی به ATM (هرچه نزدیک‌تر، وزن بیشتر)
            # قراردادهای ATM مهم‌ترن چون نقدشوندگی بیشتری دارن
            atm_weight = max(0.1, 1.0 - (distance / 20.0))  # فاصله > 20% = وزن کم
            
            # وزن نهایی
            weight = volume_weight * oi_weight * atm_weight
            
            weighted_iv_sum += iv * weight
            total_weight += weight
        
        if total_weight <= 0:
            self.wiv = None
            return None
        
        # WIV = میانگین وزنی
        self.wiv = weighted_iv_sum / total_weight
        
        # محاسبه IV/HV Ratio
        iv_hv_ratio = (self.wiv / self.hv) if (self.hv and self.hv > 0) else None
        
        # طبقه‌بندی سطح WIV
        wiv_pct = self.wiv * 100
        if wiv_pct < 30:
            wiv_level = "LOW"  # ارزان - زمان خرید
        elif wiv_pct < 50:
            wiv_level = "NORMAL"
        elif wiv_pct < 70:
            wiv_level = "ELEVATED"
        elif wiv_pct < 90:
            wiv_level = "HIGH"  # گران - زمان فروش
        else:
            wiv_level = "EXTREME"  # خیلی گران - IV Crush محتمل
        
        # طبقه‌بندی حباب
        if iv_hv_ratio:
            if iv_hv_ratio <= 1.2:
                bubble = "NONE"
            elif iv_hv_ratio <= 1.5:
                bubble = "ELEVATED"
            elif iv_hv_ratio <= 2.0:
                bubble = "HIGH"
            else:
                bubble = "EXTREME"
        else:
            bubble = "UNKNOWN"
        
        # توصیه استراتژیک
        if wiv_level in ("LOW",) and bubble in ("NONE",):
            advice = "BUY_OPTION"  # آپشن ارزانه، بخر
        elif wiv_level in ("HIGH", "EXTREME") and bubble in ("HIGH", "EXTREME"):
            advice = "SELL_OPTION"  # آپشن گرانه، بفروش
        elif wiv_level == "ELEVATED":
            advice = "CAUTION"  # احتیاط
        else:
            advice = "NEUTRAL"
        
        self.details = {
            "wiv": round(self.wiv, 4),
            "wiv_pct": round(wiv_pct, 1),
            "wiv_level": wiv_level,
            "hv": round(self.hv * 100, 1) if self.hv else None,
            "iv_hv_ratio": round(iv_hv_ratio, 2) if iv_hv_ratio else None,
            "bubble": bubble,
            "advice": advice,
            "contracts_analyzed": self.contracts_analyzed,
            "atm_contracts": len([c for c in analyzed if c["distance_pct"] < 5]),
        }
        
        # === IV Rank و Percentile ===
        # برای محاسبه دقیق نیاز به دیتای تاریخی WIV داریم
        # فعلاً از مقایسه با HV استفاده می‌کنیم
        self._estimate_iv_rank()
        
        return self.wiv
    
    def _estimate_iv_rank(self):
        """تخمین IV Rank بر اساس مقایسه با HV"""
        if not self.wiv or not self.hv:
            self.iv_rank = None
            self.iv_percentile = None
            return
        
        # تخمین ساده: اگر WIV > HV، احتمالاً IV Rank بالاست
        ratio = self.wiv / self.hv
        
        # تخمین IV Rank (0-100)
        if ratio < 0.8:
            self.iv_rank = 10
        elif ratio < 1.0:
            self.iv_rank = 30
        elif ratio < 1.2:
            self.iv_rank = 50
        elif ratio < 1.5:
            self.iv_rank = 70
        elif ratio < 2.0:
            self.iv_rank = 85
        else:
            self.iv_rank = 95
        
        # IV Percentile تقریباً مشابه IV Rank
        self.iv_percentile = self.iv_rank
        
        self.details["iv_rank"] = self.iv_rank
        self.details["iv_percentile"] = self.iv_percentile
    
    def get_signal(self):
        """تولید سیگنال بر اساس WIV"""
        if not self.details:
            return "NEUTRAL", 50, "no data"
        
        advice = self.details.get("advice", "NEUTRAL")
        wiv_level = self.details.get("wiv_level", "NORMAL")
        bubble = self.details.get("bubble", "UNKNOWN")
        
        if advice == "BUY_OPTION":
            return "BULLISH", 65, f"WIV پایین ({self.details['wiv_pct']}%) - آپشن ارزان"
        elif advice == "SELL_OPTION":
            return "BEARISH", 35, f"WIV بالا ({self.details['wiv_pct']}%) - آپشن گران"
        elif advice == "CAUTION":
            return "NEUTRAL", 45, f"WIV متوسط ({self.details['wiv_pct']}%) - احتیاط"
        else:
            return "NEUTRAL", 50, f"WIV عادی ({self.details['wiv_pct']}%)"
    
    def print_report(self):
        """چاپ گزارش کامل"""
        print("=" * 60)
        print("📊 WIV - میانگین نوسان‌پذیری ضمنی وزنی")
        print("=" * 60)
        
        if not self.details:
            print("❌ داده‌ای موجود نیست")
            return
        
        d = self.details
        print(f"  WIV:            {d['wiv_pct']}%")
        print(f"  سطح:           {d['wiv_level']}")
        print(f"  HV:             {d['hv']}%")
        print(f"  IV/HV Ratio:    {d['iv_hv_ratio']}x")
        print(f"  حباب:          {d['bubble']}")
        print(f"  IV Rank:        {d.get('iv_rank', 'N/A')}")
        print(f"  IV Percentile:  {d.get('iv_percentile', 'N/A')}")
        print(f"  توصیه:          {d['advice']}")
        print(f"  قراردادها:      {d['contracts_analyzed']}")
        print(f"  ATM:            {d['atm_contracts']}")
        print("=" * 60)


def calculate_wiv(db_name=None):
    """تابع ساده برای فراخوانی از بیرون"""
    calc = WIVCalculator(db_name)
    wiv = calc.calculate()
    return wiv, calc.details


if __name__ == "__main__":
    calc = WIVCalculator()
    wiv = calc.calculate()
    calc.print_report()
    
    if wiv:
        signal, strength, reason = calc.get_signal()
        print(f"\nسیگنال: {signal} | قدرت: {strength} | {reason}")