"""
AHRAM AI PRO - Shadow Strategy Report

این فایل فقط داده‌های خروجی AHRAM را می‌خواند و بهترین ترکیب‌های تقریبی
استراتژی را برای بررسی آزمایشی گزارش می‌کند.
هیچ دیتابیس، سیگنال، امتیاز، اطمینان یا پوزیشنی را تغییر نمی‌دهد.
"""

import argparse
import json
import math
import os
from datetime import datetime

INPUT_FILE = "ahram_strategy_data.json"
OUTPUT_FILE = "ahram_shadow_report.json"
HISTORY_FILE = "ahram_shadow_history.json"
LOT = 1000


def num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def positive(value):
    return num(value) > 0


def score_liquidity(item):
    return num(item.get("volume")) + num(item.get("open_interest"))


def best_covered_call(calls, stock):
    candidates = []
    for call in calls:
        k = num(call.get("strike_price"))
        premium = num(call.get("option_price"))
        if stock <= 0 or k <= 0 or premium <= 0 or k < stock:
            continue
        candidates.append({
            "option_symbol": call.get("symbol"),
            "strike": k,
            "premium": premium,
            "days_to_expire": call.get("days_to_expire"),
            "volume": num(call.get("volume")),
            "open_interest": num(call.get("open_interest")),
            "premium_pct_of_stock": premium / stock * 100,
            "max_profit_per_share": k + premium - stock,
            "max_profit_per_contract": (k + premium - stock) * LOT,
            "selection_role": "shadow_candidate_only",
        })
    return max(candidates, key=lambda x: (x["premium_pct_of_stock"], score_liquidity(x)), default=None)


def best_bull_call_spread(calls, stock):
    candidates = []
    ordered = sorted(calls, key=lambda x: num(x.get("strike_price")))
    for low in ordered:
        k1, p1 = num(low.get("strike_price")), num(low.get("option_price"))
        if k1 <= 0 or p1 <= 0:
            continue
        for high in ordered:
            k2, p2 = num(high.get("strike_price")), num(high.get("option_price"))
            if k2 <= k1 or p2 <= 0:
                continue
            debit = p1 - p2
            width = k2 - k1
            max_profit = width - debit
            if debit <= 0 or max_profit <= 0:
                continue
            candidates.append({
                "buy_call": low.get("symbol"), "sell_call": high.get("symbol"),
                "lower_strike": k1, "upper_strike": k2,
                "debit_per_share": debit, "max_profit_per_share": max_profit,
                "debit_per_contract": debit * LOT,
                "max_profit_per_contract": max_profit * LOT,
                "risk_reward": max_profit / debit,
                "break_even": k1 + debit,
                "days_to_expire": low.get("days_to_expire"),
                "liquidity_score": score_liquidity(low) + score_liquidity(high),
                "selection_role": "shadow_candidate_only",
            })
    return max(candidates, key=lambda x: (x["risk_reward"], x["liquidity_score"]), default=None)


def best_bull_put_spread(puts, stock):
    candidates = []
    ordered = sorted(puts, key=lambda x: num(x.get("strike_price")))
    for low in ordered:
        k1, p1 = num(low.get("strike_price")), num(low.get("option_price"))
        if k1 <= 0 or p1 <= 0:
            continue
        for high in ordered:
            k2, p2 = num(high.get("strike_price")), num(high.get("option_price"))
            if k2 <= k1 or p2 <= 0 or k2 > stock:
                continue
            credit = p2 - p1
            width = k2 - k1
            max_loss = width - credit
            if credit <= 0 or max_loss <= 0:
                continue
            candidates.append({
                "buy_put": low.get("symbol"), "sell_put": high.get("symbol"),
                "lower_strike": k1, "upper_strike": k2,
                "credit_per_share": credit, "max_loss_per_share": max_loss,
                "credit_per_contract": credit * LOT,
                "max_loss_per_contract": max_loss * LOT,
                "risk_reward": credit / max_loss,
                "break_even": k2 - credit,
                "days_to_expire": low.get("days_to_expire"),
                "liquidity_score": score_liquidity(low) + score_liquidity(high),
                "selection_role": "shadow_candidate_only",
            })
    return max(candidates, key=lambda x: (x["risk_reward"], x["liquidity_score"]), default=None)


def best_collar(calls, puts, stock):
    candidates = []
    for call in calls:
        kc, pc = num(call.get("strike_price")), num(call.get("option_price"))
        if kc < stock or pc <= 0:
            continue
        for put in puts:
            kp, pp = num(put.get("strike_price")), num(put.get("option_price"))
            if kp <= 0 or kp >= stock or pp <= 0:
                continue
            net_premium = pc - pp
            max_profit = kc - stock + net_premium
            max_loss = kp - stock + net_premium
            if max_profit <= 0:
                continue
            candidates.append({
                "sell_call": call.get("symbol"), "buy_put": put.get("symbol"),
                "call_strike": kc, "put_strike": kp,
                "net_premium_per_share": net_premium,
                "max_profit_per_share": max_profit,
                "max_loss_per_share": max_loss,
                "max_profit_per_contract": max_profit * LOT,
                "max_loss_per_contract": max_loss * LOT,
                "protection_pct": (stock - kp) / stock * 100,
                "days_to_expire": call.get("days_to_expire"),
                "liquidity_score": score_liquidity(call) + score_liquidity(put),
                "selection_role": "shadow_candidate_only",
            })
    return max(candidates, key=lambda x: (x["max_profit_per_share"], x["liquidity_score"]), default=None)


def _same_expiry_best(options, stock, calculator):
    """هر ترکیب فقط از قراردادهای دارای سررسید یکسان ساخته می‌شود."""
    groups = {}
    for item in options:
        expiry = str(item.get("expire_date") or "").strip()
        if expiry:
            groups.setdefault(expiry, []).append(item)

    candidates = []
    for expiry, group in groups.items():
        candidate = calculator(group, stock)
        if candidate:
            candidate["expiry"] = expiry
            candidates.append(candidate)

    return max(
        candidates,
        key=lambda item: (
            num(item.get("risk_reward")) or num(item.get("premium_pct_of_stock")) or num(item.get("max_profit_per_share")),
            num(item.get("liquidity_score")),
        ),
        default=None,
    )


def _calculate_covered_call(options, stock):
    calls = [x for x in options if str(x.get("option_type") or "").upper() == "CALL"]
    return best_covered_call(calls, stock)


def _calculate_bull_call_spread(options, stock):
    calls = [x for x in options if str(x.get("option_type") or "").upper() == "CALL"]
    return best_bull_call_spread(calls, stock)


def _calculate_bull_put_spread(options, stock):
    puts = [x for x in options if str(x.get("option_type") or "").upper() == "PUT"]
    return best_bull_put_spread(puts, stock)


def _calculate_collar(options, stock):
    calls = [x for x in options if str(x.get("option_type") or "").upper() == "CALL"]
    puts = [x for x in options if str(x.get("option_type") or "").upper() == "PUT"]
    # هر دو گروه از یک expiry مشترک آمده‌اند.
    return best_collar(calls, puts, stock)


def build_symbol_report(name, data):
    price = data.get("price") or {}
    stock = num(price.get("last_price")) or num(price.get("closing_price"))
    options = data.get("options") or []
    calls = [x for x in options if str(x.get("option_type") or "").upper() == "CALL"]
    puts = [x for x in options if str(x.get("option_type") or "").upper() == "PUT"]
    metrics = data.get("chain_metrics") or {}
    max_pain = data.get("max_pain") or []

    return {
        "symbol": name,
        "stock_price": stock,
        "signal": data.get("signal"),
        "chain_metrics": metrics,
        "max_pain": max_pain,
        "best_covered_call": _same_expiry_best(options, stock, _calculate_covered_call),
        "best_bull_call_spread": _same_expiry_best(options, stock, _calculate_bull_call_spread),
        "best_bull_put_spread": _same_expiry_best(options, stock, _calculate_bull_put_spread),
        "best_collar": _same_expiry_best(options, stock, _calculate_collar),
        "warning": "این خروجی Shadow است و پیشنهاد قطعی یا دستور معامله نیست.",
    }


def main():
    parser = argparse.ArgumentParser(description="Create a read-only shadow strategy report")
    parser.add_argument("--input", default=INPUT_FILE)
    parser.add_argument("--output", default=OUTPUT_FILE)
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise FileNotFoundError(f"فایل ورودی پیدا نشد: {args.input}")

    with open(args.input, "r", encoding="utf-8") as file:
        payload = json.load(file)

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "SHADOW_READ_ONLY",
        "signals_modified": False,
        "database_modified": False,
        "orders_sent": False,
        "symbols": {
            name: build_symbol_report(name, data)
            for name, data in (payload.get("symbols") or {}).items()
        },
    }

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    # آرشیو مستقل برای بک‌تست؛ اگر فایل موجود باشد فقط رکورد جدید اضافه می‌شود.
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                history = json.load(file)
            if not isinstance(history, list):
                history = []
        except (OSError, json.JSONDecodeError):
            history = []
    history.append(report)
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)

    print("✅ گزارش Shadow ساخته شد")
    print("HISTORY:", HISTORY_FILE, "| RECORDS:", len(history))
    print("OUTPUT:", args.output)
    print("MODE: SHADOW_READ_ONLY")
    for name, item in report["symbols"].items():
        found = sum(1 for key in ("best_covered_call", "best_bull_call_spread", "best_bull_put_spread", "best_collar") if item[key])
        print(f"{name}: {found}/4 shadow strategies found")


if __name__ == "__main__":
    main()
