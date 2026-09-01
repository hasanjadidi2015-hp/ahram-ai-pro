# -*- coding: utf-8 -*-
"""
AHRAM AI PRO - VACE Engine V2 - ماژول 7 از 7
اقتباس از Volumetric Adaptive Confluence Engine برای بازار ایران

این ماژول 2 قابلیت VACE را برای V5 اضافه می‌کند:
1. Auto-Calibration Engine: ADX داینامیک + ATR Factor داینامیک + SL خودکار
2. MTF Fibonacci No-Trade Zone + Break-Even + Tiered TP

فقط برای V5 Shadow - روی V4 اثری ندارد
"""

import sqlite3
import math
import numpy as np
import pandas as pd
from adx import ADX

# ==================== Auto-Calibration Engine ====================

def calculate_percentile(data, percentile=50):
    """محاسبه صدک - برای ADX threshold"""
    if not data or len(data) == 0:
        return None
    try:
        return float(np.percentile(data, percentile))
    except:
        sorted_data = sorted(data)
        k = (len(sorted_data)-1) * percentile / 100
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_data[int(k)]
        d0 = sorted_data[int(f)] * (c - k)
        d1 = sorted_data[int(c)] * (k - f)
        return d0 + d1

def get_adx_history(db_path, limit=300):
    """خواندن تاریخچه ADX از دیتابیس اگر موجود باشد، یا از prices محاسبه کن.

    نکته‌ی مهم: این تابع از همون کلاس ADX واقعی (adx.py) استفاده می‌کنه --
    همون کلاسی که current_adx بیرون از این تابع باهاش محاسبه می‌شه. قبلاً اینجا
    یه فرمول DX ساده‌ی دستی جدا داشت که هیچ ربطی به فرمول EWM/Wilder کلاس ADX
    نداشت -- یعنی صدک ۵۰ ی تاریخچه با current_adx واقعی داشت مقایسه می‌شد در
    حالی که از دو روش کاملاً متفاوت می‌اومدن (سیب با پرتقال). حالا هر دو از
    یک منبع میان و قابل‌مقایسه‌ن."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # اگر جدول adx_history وجود دارد
        try:
            cur.execute("SELECT adx FROM adx_history ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            if rows and len(rows) >= 20:
                conn.close()
                return [float(r[0]) for r in rows if r[0] is not None]
        except Exception:
            pass

        # fallback: از prices با همون کلاس ADX واقعی، روی پنجره‌ی غلتان، تاریخچه بساز
        WINDOW = 42  # ~3x دوره‌ی 14 -- برای warm-up کافی EWM، هم‌اندازه‌ی چیزی که کلاس ADX واقعی نیاز داره
        cur.execute("SELECT last_price FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT ?", (limit + WINDOW,))
        prices = cur.fetchall()
        conn.close()

        if len(prices) < WINDOW + 20:
            return None

        closes = [float(p[0]) for p in reversed(prices)]  # قدیمی به جدید

        adx_values = []
        for i in range(WINDOW, len(closes)):
            window = closes[i - WINDOW:i + 1]
            df_slice = pd.DataFrame({"last_price": window})
            adx_obj = ADX(df_slice)
            adx_obj.calculate()
            if adx_obj.adx_value:
                adx_values.append(adx_obj.adx_value)

        return adx_values[-limit:] if adx_values else None

    except Exception as e:
        print(f"[VACE] خطا get_adx_history: {e}")
        return None

def calculate_dynamic_adx_threshold(db_path, current_adx=None):
    """
    آستانه داینامیک ADX = Percentile_50(ADX_14, 300)
    از VACE Whitepaper
    """
    history = get_adx_history(db_path, limit=300)
    
    if not history or len(history) < 20:
        # fallback به مقدار ثابت قدیمی
        return {
            "threshold": 20.0,
            "current_adx": current_adx,
            "is_trending": current_adx > 20.0 if current_adx else False,
            "history_count": len(history) if history else 0,
            "method": "fallback_static_20",
            "percentile_50": 20.0
        }
    
    p50 = calculate_percentile(history, 50)
    if p50 is None:
        p50 = 20.0
    
    is_trending = False
    if current_adx is not None:
        is_trending = current_adx > p50
    
    return {
        "threshold": round(p50, 2),
        "current_adx": current_adx,
        "is_trending": is_trending,
        "history_count": len(history),
        "method": "vace_percentile_50",
        "percentile_50": round(p50, 2),
        "history_min": round(min(history), 2),
        "history_max": round(max(history), 2)
    }

def calculate_atr_percent(atr, close_price):
    """ATR_pct = (ATR_14 / Close) * 100"""
    if not atr or not close_price or close_price <= 0:
        return None
    return (atr / close_price) * 100

def calculate_volatility_adjusted_atr_factor(db_path, atr_pct_current=None, close_price=None):
    """
    Vol_ratio = ATR_pct / SMA(ATR_pct, 200)
    Vol_adj = clamp(1 - Vol_ratio, -1, 1)
    ATR_Factor = 3.8 + 0.8 * Vol_adj
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # خواندن تاریخچه ATR_pct از prices
        # ATR را از نوسان قیمت‌ها تخمین می‌زنیم
        cur.execute("SELECT last_price FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT 250")
        prices = cur.fetchall()
        conn.close()
        
        if len(prices) < 60:
            # fallback
            return {
                "atr_factor": 3.8,
                "vol_ratio": 1.0,
                "vol_adj": 0.0,
                "atr_pct": atr_pct_current,
                "method": "fallback_3.8"
            }
        
        closes = [float(p[0]) for p in reversed(prices)]
        
        # محاسبه ATR_pct history
        atr_pcts = []
        for i in range(14, len(closes)):
            window = closes[i-14:i+1]
            if len(window) < 2:
                continue
            tr = [abs(window[j] - window[j-1]) for j in range(1, len(window))]
            atr = sum(tr) / len(tr) if tr else 0
            cp = window[-1]
            if cp > 0:
                atr_pcts.append((atr / cp) * 100)
        
        if len(atr_pcts) < 20:
            return {
                "atr_factor": 3.8,
                "vol_ratio": 1.0,
                "vol_adj": 0.0,
                "atr_pct": atr_pct_current,
                "method": "fallback_3.8_short_history"
            }
        
        # SMA 200 از ATR_pct (یا هرچه موجود است)
        sma_period = min(200, len(atr_pcts))
        sma_atr_pct = sum(atr_pcts[-sma_period:]) / sma_period if sma_period > 0 else 1.0
        
        if sma_atr_pct == 0:
            sma_atr_pct = 1.0
        
        current_atr_pct = atr_pct_current
        if current_atr_pct is None:
            current_atr_pct = atr_pcts[-1] if atr_pcts else 1.0
        
        vol_ratio = current_atr_pct / sma_atr_pct if sma_atr_pct != 0 else 1.0
        vol_adj = max(min(1.0 - vol_ratio, 1.0), -1.0)
        atr_factor = 3.8 + 0.8 * vol_adj
        
        # محدود کردن بین 3 و 5 (طبق وایت‌پیپر)
        atr_factor = max(3.0, min(5.0, atr_factor))
        
        return {
            "atr_factor": round(atr_factor, 2),
            "vol_ratio": round(vol_ratio, 3),
            "vol_adj": round(vol_adj, 3),
            "atr_pct": round(current_atr_pct, 3),
            "sma_atr_pct": round(sma_atr_pct, 3),
            "method": "vace_vol_adjusted",
            "history_count": len(atr_pcts)
        }
        
    except Exception as e:
        print(f"[VACE] خطا ATR Factor: {e}")
        return {
            "atr_factor": 3.8,
            "vol_ratio": 1.0,
            "vol_adj": 0.0,
            "atr_pct": atr_pct_current,
            "method": f"error_fallback: {e}"
        }

def calculate_auto_stop_loss(db_path, atr_pct_current=None):
    """
    SL_raw = -3.5 * SMA(ATR_pct, 50)
    SL_final = clamp(SL_raw, -20%, -5%)
    """
    try:
        atr_data = calculate_volatility_adjusted_atr_factor(db_path, atr_pct_current)
        # برای SL از SMA 50 استفاده می‌کنیم
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT last_price FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT 70")
        prices = cur.fetchall()
        conn.close()
        
        if len(prices) < 20:
            return {"sl_pct": -10.0, "method": "fallback_-10%"}
        
        closes = [float(p[0]) for p in reversed(prices)]
        atr_pcts = []
        for i in range(14, len(closes)):
            window = closes[i-14:i+1]
            tr = [abs(window[j] - window[j-1]) for j in range(1, len(window))]
            atr = sum(tr) / len(tr) if tr else 0
            cp = window[-1]
            if cp > 0:
                atr_pcts.append((atr / cp) * 100)
        
        if len(atr_pcts) < 10:
            return {"sl_pct": -10.0, "method": "fallback_-10%_short"}
        
        sma_50 = sum(atr_pcts[-50:]) / min(50, len(atr_pcts))
        sl_raw = -3.5 * sma_50
        sl_final = max(min(sl_raw, -5.0), -20.0)
        
        return {
            "sl_pct": round(sl_final, 2),
            "sl_raw": round(sl_raw, 2),
            "sma_atr_pct_50": round(sma_50, 3),
            "method": "vace_auto_sl"
        }
    except Exception as e:
        return {"sl_pct": -10.0, "method": f"error_fallback: {e}"}

# ==================== MTF Fibonacci Filter ====================

def analyze_fibo_no_trade_zone(fib_details, current_price):
    """
    فیلتر فیبوناچی چندزمانی VACE:
    - Mid Zone 38.2%-61.8% = No Trade
    - Shallow Zone <38.2% = مجاز ولی TP1 override به 38.2%
    - Deep Zone >61.8% = مجاز با ATR عادی
    """
    if not fib_details or not current_price:
        return {
            "allow_entry": True,
            "zone": "UNKNOWN",
            "reason": "داده فیبوناچی کافی نیست",
            "tp1_override": None
        }
    
    try:
        levels = fib_details.get("levels", {})
        if not levels:
            return {"allow_entry": True, "zone": "UNKNOWN", "reason": "سطوح فیبو موجود نیست", "tp1_override": None}
        
        # سطوح 38.2 و 61.8
        level_382 = levels.get("0.382")
        level_618 = levels.get("0.618")
        
        if level_382 is None or level_618 is None:
            return {"allow_entry": True, "zone": "UNKNOWN", "reason": "سطوح 38.2/61.8 موجود نیست", "tp1_override": None}
        
        # تعیین بازه Mid Zone (بین 38.2 و 61.8)
        low_mid = min(level_382, level_618)
        high_mid = max(level_382, level_618)
        
        # تشخیص زون
        if low_mid <= current_price <= high_mid:
            # Mid Zone - No Trade
            return {
                "allow_entry": False,
                "zone": "MID_ZONE_NO_TRADE",
                "reason": f"قیمت {current_price} در زون ممنوعه فیبو {low_mid:.0f}-{high_mid:.0f} (38.2%-61.8%) - ورود ممنوع",
                "tp1_override": None,
                "level_382": level_382,
                "level_618": level_618
            }
        elif (current_price < low_mid and fib_details.get("trend") == "UP") or (current_price > high_mid and fib_details.get("trend") == "DOWN"):
            # Shallow Zone - مجاز ولی TP1 override
            return {
                "allow_entry": True,
                "zone": "SHALLOW_ZONE",
                "reason": f"قیمت {current_price} در زون کم‌عمق - ورود مجاز ولی TP1 روی 38.2% ({level_382:.0f})",
                "tp1_override": level_382,
                "level_382": level_382,
                "level_618": level_618
            }
        else:
            # Deep Zone - مجاز عادی
            return {
                "allow_entry": True,
                "zone": "DEEP_ZONE",
                "reason": f"قیمت {current_price} در زون عمیق - ورود با ATR عادی",
                "tp1_override": None,
                "level_382": level_382,
                "level_618": level_618
            }
            
    except Exception as e:
        return {
            "allow_entry": True,
            "zone": "ERROR",
            "reason": f"خطا تحلیل فیبو: {e}",
            "tp1_override": None
        }

# ==================== Position Management ====================

def calculate_tiered_tp(entry_price, atr_value, atr_factor, option_type="CALL"):
    """
    TP1 = Entry + ATR * Factor
    TP2 = Entry + ATR * Factor * 2
    TP3 = Entry + ATR * Factor * 3
    هر کدام 30% بستن (Partial Close)
    """
    if not entry_price or entry_price <= 0 or not atr_value:
        return None
    
    try:
        tp1 = entry_price + (atr_value * atr_factor)
        tp2 = entry_price + (atr_value * atr_factor * 2)
        tp3 = entry_price + (atr_value * atr_factor * 3)
        
        # برای PUT برعکس؟ در آپشن خرید، هر دو CALL و PUT با افزایش قیمت آپشن سود می‌دهند
        # پس TP برای هر دو به سمت بالا
        # ولی اگر بخواهیم برای PUT آپشن، قیمت آپشن با ریزش سهم بالا می‌ره، باز هم TP بالاست
        
        return {
            "tp1": round(tp1),
            "tp1_pct": round(((tp1 - entry_price) / entry_price) * 100, 1),
            "tp1_close_pct": 30,
            "tp2": round(tp2),
            "tp2_pct": round(((tp2 - entry_price) / entry_price) * 100, 1),
            "tp2_close_pct": 30,
            "tp3": round(tp3),
            "tp3_pct": round(((tp3 - entry_price) / entry_price) * 100, 1),
            "tp3_close_pct": 40,
            "atr_factor": atr_factor,
            "atr_value": atr_value,
            "method": "vace_tiered_tp"
        }
    except Exception as e:
        print(f"[VACE] خطا Tiered TP: {e}")
        return None

def check_break_even(pnl_pct, be_threshold=8.5):
    """
    اگر PnL >= 8.5%، SL به قیمت ورود منتقل می‌شود (Risk-Free)
    """
    return pnl_pct >= be_threshold

# ==================== موتور اصلی ====================

def analyze_vace(db_path, current_adx=None, atr=None, close_price=None, fib_details=None, current_price=None):
    """
    تحلیل کامل VACE برای یک نماد
    """
    result = {}
    
    # 1. Dynamic ADX
    result["dynamic_adx"] = calculate_dynamic_adx_threshold(db_path, current_adx)
    
    # 2. ATR Factor
    atr_pct = calculate_atr_percent(atr, close_price) if atr and close_price else None
    result["atr_factor"] = calculate_volatility_adjusted_atr_factor(db_path, atr_pct, close_price)
    
    # 3. Auto SL
    result["auto_sl"] = calculate_auto_stop_loss(db_path, atr_pct)
    
    # 4. Fibo No-Trade Zone
    if fib_details and current_price:
        result["fibo_filter"] = analyze_fibo_no_trade_zone(fib_details, current_price)
    else:
        result["fibo_filter"] = {"allow_entry": True, "zone": "NO_DATA", "reason": "فیبو موجود نیست"}
    
    # خلاصه
    adx_ok = result["dynamic_adx"]["is_trending"]
    fibo_ok = result["fibo_filter"]["allow_entry"]
    
    result["confluence_ok"] = adx_ok and fibo_ok
    result["summary"] = f"ADX Trending: {adx_ok} (threshold {result['dynamic_adx']['threshold']}) | Fibo Allow: {fibo_ok} ({result['fibo_filter']['zone']}) | ATR Factor: {result['atr_factor']['atr_factor']}"
    
    return result

# ==================== تست ====================

if __name__ == "__main__":
    print("VACE Engine V2 Test")
    print("="*60)
    
    # تست با DB فرضی - اگر وجود نداشته باشد fallback می‌دهد
    test_db = "ahram_v2.db"
    if not __import__("os").path.exists(test_db):
        test_db = "ahram_v2_v5.db"
    
    print(f"\n--- Test with {test_db} ---")
    vace = analyze_vace(test_db, current_adx=35, atr=500, close_price=59000, current_price=59000)
    
    print(f"\nDynamic ADX: {vace['dynamic_adx']}")
    print(f"ATR Factor: {vace['atr_factor']}")
    print(f"Auto SL: {vace['auto_sl']}")
    print(f"Fibo Filter: {vace['fibo_filter']}")
    print(f"Confluence OK: {vace['confluence_ok']}")
    print(f"Summary: {vace['summary']}")
    
    print("\n--- Test Tiered TP ---")
    tp = calculate_tiered_tp(5300, 200, 3.8)
    print(f"Tiered TP: {tp}")
    
    print("\n--- Test Break-Even ---")
    print(f"PnL 5% -> BE? {check_break_even(5)}")
    print(f"PnL 8.5% -> BE? {check_break_even(8.5)}")
    print(f"PnL 15% -> BE? {check_break_even(15)}")