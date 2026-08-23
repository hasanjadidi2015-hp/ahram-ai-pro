# -*- coding: utf-8 -*-
"""
GAMMA EXPOSURE / فشار فروشنده پوت -- شاخص اکتشافی (نه تصمیم‌گیر مستقیم)

این ماژول گاما رو برای کل زنجیره‌ی آپشن یه نماد حساب می‌کنه و باهاش دو چیز
می‌سازه:
  1. «دیواره‌ی گاما» (gamma wall): Strikeـی که بیشترین تجمع گاما×OI روش
     هست -- معمولاً به‌عنوان سطح احتمالی pinning/محدودکننده‌ی نوسان دیده
     می‌شه (هرچه سررسید نزدیک‌تر، اثرش قوی‌تر -- که خودش توی فرمول گاما
     لحاظ شده، چون گاما نزدیک سررسید و نزدیک ATM بیشتره).
  2. یه بایاس نسبی رژیم (CALL_HEAVY / PUT_HEAVY / BALANCED) بر پایه‌ی
     قرارداد متداول GEX: Call OI×Gamma منهای Put OI×Gamma.

⚠️ هشدار مهم -- حتماً قبل از تصمیم‌گیری بر اساسش بخون:
این شاخص بر پایه‌ی فرضیات بازارهای بزرگ جهانی ساخته شده (اینکه مارکت‌میکرها
طرف مقابل اغلب معاملات هستن و به‌صورت سیستماتیک دلتاهج می‌کنن). همون‌طور که
قبلاً بحث شد: صرفاً موقعیت باز نمی‌گه ریسک دست کیه یا اون بازیگر اصلاً هج
می‌کنه یا نه. توی بازار آپشن ایران که کوچیک‌تر و کم‌عمق‌تره، این فرض‌ها ممکنه
برقرار نباشن.

برای همین این ماژول:
  - فعلاً فقط اطلاعاتی/نمایشیه -- به امتیاز نهایی BUY/SELL اضافه نمی‌شه.
  - توصیه می‌شه چند هفته این خروجی‌ها رو کنار رفتار واقعی قیمت observe کنی؛
    اگه دیدی واقعاً هم‌خونی داره (مثلاً قیمت واقعاً نزدیک دیواره‌ی گاما
    متوقف می‌شه)، اون‌موقع می‌شه بهش وزن داد توی تصمیم‌گیری.
  - فیلد confidence نشون می‌ده چقدر داده‌ی پشتش نقدشونده‌ست؛ وقتی LOW باشه
    یعنی OI بیشتر روی strikeهای بی‌معامله نشسته و به عدد نباید خیلی اعتماد کرد.
"""
import sqlite3

from option_engine import OptionEngine
import config


def _latest_chain(db_path):
    """آخرین اسنپ‌شات کامل زنجیره‌ی آپشن (همه‌ی strike ها، CALL و PUT)."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT MAX(time) FROM options")
        mt = cur.fetchone()[0]
        if not mt:
            conn.close()
            return [], None
        cur.execute(
            "SELECT symbol, option_type, stock_price, strike_price, option_price, "
            "days_to_expire, volume, open_interest FROM options WHERE time=?",
            (mt,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows, mt
    except Exception:
        return [], None


def analyze_gamma_exposure(db_path, stock_price=None, risk_free=None):
    rows, snapshot_time = _latest_chain(db_path)
    empty = {
        "gamma_wall": None, "regime_bias": "UNKNOWN", "bias_pct": 0,
        "confidence": "LOW", "snapshot_time": snapshot_time, "details": {},
    }
    if not rows:
        return empty

    eng = OptionEngine()
    r = risk_free if risk_free is not None else config.RISK_FREE_RATE
    hv = config.BLACK_SCHOLES_VOL

    strike_gamma = {}
    call_gamma_oi = 0.0
    put_gamma_oi = 0.0
    total_oi = 0.0
    liquid_oi = 0.0

    for sym, otype, spot, strike, opt_price, dte, vol, oi in rows:
        try:
            S = float(spot) if spot else (float(stock_price) if stock_price else 0)
            K = float(strike) if strike else 0
            T = max(float(dte), 0) / 365.0 if dte is not None else 0
            oi_f = float(oi) if oi else 0.0
            vol_f = float(vol) if vol else 0.0
            if S <= 0 or K <= 0 or T <= 0 or oi_f <= 0:
                continue

            sigma = hv
            if opt_price and float(opt_price) > 0:
                iv = eng._implied_vol(float(opt_price), S, K, T, r, otype, verbose=False)
                if iv and iv > 0:
                    sigma = iv

            g = eng._bs(S, K, T, r, sigma, otype)["gamma"]
            if not g or g != g:  # گارد NaN
                continue

            weighted = oi_f * g
            strike_gamma[K] = strike_gamma.get(K, 0.0) + weighted
            total_oi += oi_f
            if vol_f > 0:
                liquid_oi += oi_f

            if otype == "CALL":
                call_gamma_oi += weighted
            elif otype == "PUT":
                put_gamma_oi += weighted
        except Exception:
            continue

    if not strike_gamma or total_oi <= 0:
        return empty

    gamma_wall = max(strike_gamma, key=strike_gamma.get)

    net = call_gamma_oi - put_gamma_oi
    base = call_gamma_oi + put_gamma_oi
    bias_pct = (net / base * 100) if base > 0 else 0
    if bias_pct > 15:
        regime_bias = "CALL_HEAVY"
    elif bias_pct < -15:
        regime_bias = "PUT_HEAVY"
    else:
        regime_bias = "BALANCED"

    liquidity_ratio = (liquid_oi / total_oi) if total_oi > 0 else 0
    if liquidity_ratio >= 0.5:
        confidence = "HIGH"
    elif liquidity_ratio >= 0.2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "gamma_wall": gamma_wall,
        "regime_bias": regime_bias,
        "bias_pct": round(bias_pct, 1),
        "confidence": confidence,
        "snapshot_time": snapshot_time,
        "details": {
            "call_gamma_oi": round(call_gamma_oi, 2),
            "put_gamma_oi": round(put_gamma_oi, 2),
            "total_oi": round(total_oi, 1),
            "liquidity_ratio": round(liquidity_ratio, 2),
            "strikes_considered": len(strike_gamma),
        },
    }


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else config.DATABASE_NAME
    result = analyze_gamma_exposure(db)
    print("=" * 50)
    print("GAMMA EXPOSURE (اکتشافی -- روی امتیاز اثر نمی‌ذاره)")
    print("=" * 50)
    print(f"دیواره‌ی گاما (strike): {result['gamma_wall']}")
    print(f"بایاس رژیم: {result['regime_bias']} ({result.get('bias_pct')}%)")
    print(f"اطمینان (نقدشوندگی داده): {result['confidence']}")
    print(f"جزئیات: {result['details']}")