# -*- coding: utf-8 -*-
class OptionDecision:
    def __init__(self):
        pass

    def decide(self, stock_action, stock_confidence, option_data):
        score = 0
        reasons = []
        symbol = option_data.get("symbol", "")
        option_type = option_data.get("option_type", "CALL")
        data_quality = option_data.get("data_quality", "OK")
        valuation = option_data.get("valuation", "")
        delta = abs(option_data.get("delta", 0) or 0)
        fair_value = option_data.get("fair_value", 0)
        option_price = option_data.get("option_price", 0)
        volume = option_data.get("volume", 0) or 0
        rr = option_data.get("risk_reward_ratio", 0) or 0
        iv_crush_risk = option_data.get("iv_crush_risk", False)
        iv_premium_ratio = option_data.get("iv_premium_ratio", 0) or 0
        try:
            distance_pct = abs(float(option_data.get("distance_pct", 99)))
        except (TypeError, ValueError):
            distance_pct = 99.0

        if data_quality == "INVALID":
            return {"action": "REJECT OPTION DATA", "confidence": 0, "score": -100,
                    "reasons": ["INVALID OPTION PRICE", *option_data.get("warnings", [])]}

        # تمایلِ سهم — CALL: BUY خوبه / PUT: SELL خوبه ✅ (اصلاحِ اصلی)
        if option_type == "PUT":
            if stock_action in ["STRONG SELL", "SELL"]:
                score += 25; reasons.append("STOCK TREND SELL -> PUT favorable")
            elif stock_action in ["STRONG BUY", "BUY"]:
                score -= 25; reasons.append("STOCK TREND BUY -> PUT unfavorable")
        else:  # CALL
            if stock_action in ["STRONG BUY", "BUY"]:
                score += 25; reasons.append("STOCK TREND BUY")
            elif stock_action in ["STRONG SELL", "SELL"]:
                score -= 25; reasons.append("STOCK TREND SELL")

        if stock_confidence >= 65:
            score += 20; reasons.append("HIGH STOCK CONFIDENCE")
        elif stock_confidence < 45:
            score -= 10; reasons.append("LOW STOCK CONFIDENCE")

        # ارزش‌گذاری (ملایم‌تر شد: -30 → -15)
        if valuation == "UNDERVALUED":
            score += 20; reasons.append("OPTION BELOW FAIR VALUE")
        elif valuation == "OVERVALUED":
            score -= 15; reasons.append("OPTION slightly expensive")
        elif valuation == "FAIR":
            score += 5; reasons.append("OPTION FAIRLY PRICED")

        # دلتا (باندِ 0.35-0.45 اضافه شد)
        if delta > 0.85:
            score -= 35; reasons.append("DEEP ITM - no leverage")
        elif delta > 0.75:
            score -= 15; reasons.append("deep ITM - low leverage")
        elif 0.45 <= delta <= 0.70:
            score += 15; reasons.append("GOOD DELTA (ATM zone)")
        elif 0.35 <= delta < 0.45:
            score += 5; reasons.append("acceptable delta")
        elif delta < 0.35:
            score -= 15; reasons.append("LOW DELTA (far OTM)")

        # ریسک/بازده (ملایم‌تر شد: قبلاً rr<0.8 یه -50 می‌گرفت!)
        if rr > 0:
            if rr < 0.5:
                score -= 40; reasons.append("BAD RISK/REWARD (%.2f)" % rr)
            elif rr < 0.8:
                score -= 20; reasons.append("WEAK RISK/REWARD (%.2f)" % rr)
            elif rr >= 2.0:
                score += 25; reasons.append("EXCELLENT RISK/REWARD (%.2f)" % rr)
            elif rr >= 1.5:
                score += 15; reasons.append("GOOD RISK/REWARD (%.2f)" % rr)
            # 0.8 <= rr < 1.5: خنثی

        # نزدیک ATM
        if distance_pct < 3:
            score += 25; reasons.append("NEAR ATM (best for scalping)")
        elif distance_pct < 5:
            score += 15; reasons.append("close to ATM")

        # IV crush (فقط حبابِ شدید)
        if iv_crush_risk:
            if iv_premium_ratio > 4.0:
                score -= 40; reasons.append("IV EXTREME - overpaying risk")
            elif iv_premium_ratio > 2.5:
                score -= 20; reasons.append("IV HIGH - caution")

        # نقدشوندگی
        if volume >= 50000:
            score += 10; reasons.append("OPTION LIQUID")
        else:
            score -= 5; reasons.append("LOW OPTION VOLUME")

        confidence = max(0, min(100, score + 45))

        if score >= 50 and stock_confidence >= 60:
            action = "BUY OPTION"
        elif score >= 30:
            action = "WATCH OPTION"
        else:
            action = "WAIT"

        return {"action": action, "confidence": confidence, "score": score,
                "reasons": reasons, "symbol": symbol,
                "fair_value": fair_value, "delta": delta}