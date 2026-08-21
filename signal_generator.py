# -*- coding: utf-8 -*-
"""AHRAM SIGNAL GENERATOR - مغز تولید سیگنال تجمیعی"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import config as _config
    _BUY_TH = getattr(_config, "COMPOSITE_BUY_THRESHOLD", 70)
except Exception:
    _BUY_TH = 70

_WATCH_TH = 55


def compute_option_targets(entry_price, days_to_expire, style="mixed"):
    try:
        entry_price = float(entry_price)
    except (ValueError, TypeError):
        entry_price = 0.0
    if entry_price <= 0:
        return None
    try:
        dte = int(days_to_expire)
    except (ValueError, TypeError):
        dte = 30
    if dte <= 14:
        stop_pct = 0.08
    elif dte <= 30:
        stop_pct = 0.10
    else:
        stop_pct = 0.12
    if style == "fast":
        t1, t2 = 0.08, 0.15
    elif style == "swing":
        t1, t2 = 0.20, 0.40
    else:
        t1, t2 = 0.10, 0.25
    return {
        "stop_loss": round(entry_price * (1 - stop_pct)),
        "stop_pct": round(stop_pct * 100),
        "target1": round(entry_price * (1 + t1)),
        "target1_pct": round(t1 * 100),
        "target2": round(entry_price * (1 + t2)),
        "target2_pct": round(t2 * 100),
    }


def _fmt(n):
    try:
        return f"{int(round(float(n))):,}"
    except (ValueError, TypeError):
        return str(n)


def compute_composite_score(stock_action, stock_confidence, stock_score,
                            option_decision, indices=None, money_flow=None):
    try:
        ss = float(stock_score)
    except (ValueError, TypeError):
        ss = 0.0
    strategy_pts = max(0.0, min(50.0, (abs(ss) / 100.0) * 50.0))
    if option_decision and option_decision.get("action") == "BUY OPTION":
        oc = float(option_decision.get("confidence", 0) or 0)
        option_pts = max(0.0, min(30.0, (oc / 100.0) * 30.0))
    elif option_decision:
        oc = float(option_decision.get("confidence", 0) or 0)
        option_pts = max(0.0, min(15.0, (oc / 100.0) * 15.0))
    else:
        option_pts = 0.0
    index_pts = 5.0
    if indices:
        total = indices.get("شاخص کل") or indices.get("شاخص كل")
        if total and total.get("change_pct") is not None:
            chg = float(total["change_pct"])
            if chg > 0.5:
                index_pts = 10.0
            elif chg < -0.5:
                index_pts = 0.0
            else:
                index_pts = 5.0
    money_pts = 5.0
    if money_flow:
        net_inst = money_flow.get("net_institutional_volume")
        if net_inst is not None:
            if float(net_inst) > 0:
                money_pts = 10.0
            elif float(net_inst) < 0:
                money_pts = 0.0
    market_pts = index_pts + money_pts
    total = strategy_pts + option_pts + market_pts
    total = max(0.0, min(100.0, total))
    return {"total": round(total), "strategy_pts": round(strategy_pts),
            "option_pts": round(option_pts), "market_pts": round(market_pts)}


def _decide(stock_action, option_decision, composite):
    total = composite["total"]
    opt_action = option_decision.get("action") if option_decision else None
    if stock_action in ("BUY", "STRONG BUY") and opt_action == "BUY OPTION" and total >= _BUY_TH:
        return "BUY"
    if stock_action in ("SELL", "STRONG SELL") and opt_action == "BUY OPTION" and total >= _BUY_TH:
        return "BUY"
    if total >= _WATCH_TH:
        return "WATCH"
    return "WAIT"


def generate_signal(stock_action, stock_confidence, stock_score, price,
                    option_decision=None, indices=None, money_flow=None, style="mixed"):
    composite = compute_composite_score(stock_action, stock_confidence, stock_score,
                                        option_decision, indices, money_flow)
    signal_type = _decide(stock_action, option_decision, composite)
    underlying = getattr(_config, "UNDERLYING", "اهرم") if _config else "اهرم"
    if option_decision:
        oc = float(option_decision.get("confidence", 0) or 0)
        confidence = round(0.6 * composite["total"] + 0.4 * oc)
    else:
        confidence = round(composite["total"] * 0.7)
    result = {"type": signal_type, "score": composite["total"], "confidence": confidence,
              "breakdown": composite, "option_decision": option_decision,
              "price": price, "stock_action": stock_action, "message": ""}
    lines = []
    bar = "━" * 46

    if signal_type == "BUY" and option_decision:
        targets = compute_option_targets(option_decision.get("option_price"),
                                         option_decision.get("days_to_expire"), style)
        opt_type_fa = "کال (خرید)" if option_decision.get("option_type") == "CALL" else "پوت (فروش)"
        reasons = option_decision.get("reasons", [])
        lines.append("╔" + "═" * 46 + "╗")
        lines.append("║" + "  🟢  سیگنال خرید  ( BUY OPTION )  ".center(40) + "║")
        lines.append("╚" + "═" * 46 + "╝")
        lines.append("")
        lines.append(f"📊 امتیاز کل: {composite['total']} / 100")
        lines.append(f"✅ میزان اطمینان: {confidence} %")
        lines.append("")
        lines.append(f"📈 {underlying}: {_fmt(price)} ریال")
        lines.append(f"   سیگنال سهم: {stock_action} ({stock_confidence}% اطمینان)")
        lines.append("")
        lines.append(f"🎯 بهترین قرارداد: {option_decision.get('symbol')} ({opt_type_fa})")
        lines.append(f"   • قیمت اعمال: {_fmt(option_decision.get('strike_price'))} | "
                     f"سررسید: {option_decision.get('expire_date')} ({option_decision.get('days_to_expire')} روز مانده)")
        lines.append(f"   • قیمت اپشن: {_fmt(option_decision.get('option_price'))} | دلتا: {option_decision.get('delta')}")
        lines.append(f"   • ارزش منصفانه: {_fmt(option_decision.get('fair_value'))} | احتمال سود: {option_decision.get('probability_of_profit')}%")
        _eep = option_decision.get("early_exercise_premium")
        _fva = option_decision.get("fair_value_american")
        if _eep is not None and _fva is not None and abs(_eep) >= 1:
            lines.append(f"   • ارزش منصفانه (آمریکایی): {_fmt(_fva)}  (صرف اعمال زودهنگام: {_eep:+.2f})")
        if targets:
            option_decision["stop_loss"] = targets["stop_loss"]
            option_decision["target1"] = targets["target1"]
            option_decision["target2"] = targets["target2"]
        lines.append("")
        if targets:
            lines.append(f"🛑 حد ضرر:          {_fmt(targets['stop_loss'])}  (−{targets['stop_pct']}%)")
            lines.append(f"🎯 هدف اول (سریع):  {_fmt(targets['target1'])}  (+{targets['target1_pct']}%) → نصف حجم بفروش")
            lines.append(f"🚀 هدف دوم (میان‌مدت): {_fmt(targets['target2'])}  (+{targets['target2_pct']}%) → بقیه حجم")
            try:
                capital = getattr(_config, "INITIAL_CAPITAL", 100000000)
                risk_pct = getattr(_config, "RISK_PER_TRADE", 0.02)
                risk_budget = capital * risk_pct
                entry_p = float(option_decision.get("option_price", 0) or 0)
                stop_p = float(targets["stop_loss"])
                risk_per_unit = max(1.0, entry_p - stop_p)
                max_units = int(risk_budget / risk_per_unit)
                lines.append("")
                lines.append(f"💼 حجم پیشنهادی: ~{max_units:,} واحد")
                lines.append(f"   (ریسک {risk_pct * 100:.0f}٪ سرمایه = {risk_budget:,.0f} ریال)")
            except Exception:
                pass
        lines.append("")
        lines.append(f"📋 تفکیک امتیاز: سهم {composite['strategy_pts']}/۵۰ + آپشن {composite['option_pts']}/۳۰ + بازار {composite['market_pts']}/۲۰")
        if reasons:
            lines.append("📋 دلایل: " + "، ".join(reasons))
        lines.append(bar)
    elif signal_type == "WATCH":
        lines.append(bar)
        lines.append("🟡  وضعیت: WATCH (تحت نظر)")
        lines.append(bar)
        lines.append(f"📊 امتیاز کل: {composite['total']} / 100")
        lines.append(f"✅ میزان اطمینان: {confidence} %")
        lines.append(f"📈 {underlying}: {_fmt(price)} ریال | سیگنال سهم: {stock_action}")
        lines.append("")
        lines.append("شرایط در حال شکل‌گیری است. فعلاً معامله نکن.")
        missing = []
        if composite["strategy_pts"] < 30:
            missing.append("هم‌جهتی بیشتر اندیکاتورهای سهم")
        if composite["option_pts"] < 15:
            missing.append("تأیید بهتر از آپشن")
        if composite["market_pts"] < 12:
            missing.append("تأیید فضای بازار")
        if missing:
            lines.append("🔍 برای ارتقا به خرید لازم است: " + "، ".join(missing))
        lines.append(bar)
    else:
        lines.append(bar)
        lines.append("⚪  وضعیت: WAIT (صبر کن)")
        lines.append(bar)
        lines.append(f"📊 امتیاز کل: {composite['total']} / 100")
        lines.append(f"📈 {underlying}: {_fmt(price)} ریال | سیگنال سهم: {stock_action}")
        lines.append("شرایط برای معامله مهیا نیست. صبر کن.")
        lines.append(bar)
    result["message"] = "\n".join(lines)
    return result


if __name__ == "__main__":
    sample = {"action": "BUY OPTION", "confidence": 85, "symbol": "ضملت5031", "option_type": "CALL",
              "strike_price": 1154, "option_price": 82, "expire_date": "1405/06/13", "days_to_expire": 8,
              "delta": 0.55, "fair_value": 70, "probability_of_profit": 50,
              "reasons": ["روند صعودی", "حجم بالا"], "distance_pct": -4, "risk_reward_ratio": 3.0}
    sig = generate_signal("BUY", 75, 57, 1199, sample, None, None, "mixed")
    print(sig["message"])