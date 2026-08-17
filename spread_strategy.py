# -*- coding: utf-8 -*-
import sqlite3
from collections import defaultdict
from option_engine import OptionEngine


def find_best_spread(stock_price, db):
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT MAX(time) FROM options")
        r = cur.fetchone()
        latest = r[0] if r else None
        if not latest:
            conn.close(); return None
        cur.execute("SELECT symbol,strike_price,option_price,days_to_expire,volume FROM options WHERE option_type='CALL' AND time=? AND volume>0 AND option_price>0 AND days_to_expire>=7 ORDER BY strike_price", (latest,))
        opts = cur.fetchall()
        conn.close()
    except Exception:
        return None
    if len(opts) < 2 or not stock_price or stock_price <= 0:
        return None
    eng = OptionEngine()
    analyzed = []
    for sym, strike, price, dte, vol in opts:
        try:
            a = eng.analyze(float(stock_price), float(strike), float(price), int(dte or 0), "CALL", float(vol or 0))
        except Exception:
            continue
        a["symbol"] = sym
        analyzed.append(a)
    by_exp = defaultdict(list)
    for a in analyzed:
        by_exp[a["days_to_expire"]].append(a)
    best = None
    for dte, legs in by_exp.items():
        legs.sort(key=lambda x: x["strike_price"])
        for i, long_leg in enumerate(legs):
            ld = long_leg.get("delta", 0)
            if not (0.50 <= ld <= 0.72):
                continue
            if long_leg["strike_price"] > stock_price:
                continue
            for short_leg in legs[i + 1:]:
                sd = short_leg.get("delta", 0)
                if not (0.15 <= sd <= 0.40):
                    continue
                net_debit = long_leg["option_price"] - short_leg["option_price"]
                if net_debit <= 0:
                    continue
                width = short_leg["strike_price"] - long_leg["strike_price"]
                if width <= 0:
                    continue
                if width > stock_price * 0.15:
                    continue
                max_profit = width - net_debit
                if max_profit <= 0:
                    continue
                rr = max_profit / net_debit
                spread = {"long_symbol": long_leg["symbol"], "short_symbol": short_leg["symbol"], "long_strike": long_leg["strike_price"], "short_strike": short_leg["strike_price"], "long_price": long_leg["option_price"], "short_price": short_leg["option_price"], "net_debit": round(net_debit, 1), "width": width, "max_profit": round(max_profit, 1), "max_loss": round(net_debit, 1), "risk_reward": round(rr, 2), "breakeven": round(long_leg["strike_price"] + net_debit, 1), "days_to_expire": dte, "stock_price": stock_price, "long_delta": ld}
                if best is None or rr > best["risk_reward"]:
                    best = spread
    return best


def build_spread_signal(stock_price, db, stock_name="", stock_confidence=85):
    sp = find_best_spread(stock_price, db)
    if not sp or sp["risk_reward"] < 0.7:
        return None
    net_debit = sp["net_debit"]
    max_profit = sp["max_profit"]
    target1 = round(net_debit + 0.5 * max_profit, 1)
    target2 = round(net_debit + max_profit, 1)
    stop = round(net_debit * 0.5, 1)
    score = min(100, int(40 + sp["risk_reward"] * 12))
    confidence = min(100, int(50 + sp["risk_reward"] * 8))
    od = {"action": "BUY OPTION", "confidence": confidence, "score": score, "symbol": sp["long_symbol"], "symbol_short": sp["short_symbol"], "option_type": "SPREAD", "option_price": net_debit, "strike_price": sp["long_strike"], "stop_loss": stop, "target1": target1, "target2": target2, "days_to_expire": sp["days_to_expire"], "delta": sp["long_delta"], "fair_value": net_debit, "risk_reward_ratio": sp["risk_reward"], "reasons": ["BULL CALL SPREAD (IV-protected)", "buy %s @ %s + sell %s @ %s" % (sp["long_symbol"], sp["long_price"], sp["short_symbol"], sp["short_price"]), "debit %s | max profit %s | max loss %s | R/R %.2f" % (net_debit, max_profit, sp["max_loss"], sp["risk_reward"])]}
    bar = "=" * 50
    lines = [bar, "GREEN BUY: BULL CALL SPREAD (%s)" % stock_name, bar, "long: %s strike %s @ %s" % (sp["long_symbol"], int(sp["long_strike"]), int(sp["long_price"])), "short: %s strike %s @ %s" % (sp["short_symbol"], int(sp["short_strike"]), int(sp["short_price"])), "net debit: %s | max profit: %s | max loss: %s | R/R %.2f" % (int(net_debit), int(max_profit), int(sp["max_loss"]), sp["risk_reward"]), "target1: %s | target2: %s | stop: %s" % (int(target1), int(target2), int(stop)), bar]
    return {"type": "BUY", "score": score, "confidence": confidence, "stock_confidence": stock_confidence, "stock_score": 80, "breakdown": {"total": score}, "option_decision": od, "price": stock_price, "stock_action": "BUY", "spread": sp, "message": "\n".join(lines)}


def current_spread_value(long_symbol, short_symbol, db):
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        lp = cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (long_symbol,)).fetchone()
        sp_ = cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (short_symbol,)).fetchone()
        conn.close()
        if not lp or not sp_ or not lp[0] or not sp_[0]:
            return None
        return round(float(lp[0]) - float(sp_[0]), 1)
    except Exception:
        return None