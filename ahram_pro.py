# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║              AHRAM AI PRO v4.1 - نسخه نهایی                 ║
║         سیستم معامله‌گری تجمیعی آپشن بورس ایران              ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys
import sqlite3
import time
import json
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except:
    pass

try:
    import ml_adjust
    _HAS_ML = True
except Exception as _e:
    ml_adjust = None
    _HAS_ML = False
    print(f"[WARN] ml_adjust بارگذاری نشد: {_e}")

try:
    from gamma_exposure import analyze_gamma_exposure
    _HAS_GAMMA = True
except Exception as _e:
    analyze_gamma_exposure = None
    _HAS_GAMMA = False
    print(f"[WARN] gamma_exposure بارگذاری نشد: {_e}")

try:
    from iv_rank import record_daily_iv, compute_iv_rank_percentile, MIN_DAYS as _IV_MIN_DAYS
    _HAS_IVRANK = True
except Exception as _e:
    record_daily_iv = compute_iv_rank_percentile = None
    _IV_MIN_DAYS = 10
    _HAS_IVRANK = False
    print(f"[WARN] iv_rank بارگذاری نشد: {_e}")

CONFIG = {
    "version": "4.1",
    "name": "AHRAM AI PRO",
    "symbols": [
        {"name": "اهرم", "ins_code": "17914401175772326", "db": "ahram_v2.db", "option_root": "هرم", "queue_gap": 4.0},
        {"name": "وبملت", "ins_code": "778253364357513", "db": "webmellt.db", "option_root": "ملت", "queue_gap": 7.0},
        {"name": "شستا", "ins_code": "2400322364771558", "db": "shasta.db", "option_root": "ستا", "queue_gap": 7.0},
    ],
    "market_open": dtime(9, 0),
    "market_close": dtime(12, 30),
    "cycle_seconds": 300,
    "min_score": 45,
    "min_indicators": 3,
    "min_volume_ratio": 1.0,
    "max_wiv_for_buy": 85,
    "max_positions": 3,
    "max_position_hold_hours": 3,   # بعد از این مدت، پوزیشن باز-فرض‌شده منقضی می‌شه
    "risk_per_trade": 0.05,
    "capital": 100_000_000,
    "telegram_enabled": False,
    "desktop_enabled": True,
    "dashboard_enabled": True,
}


class SystemState:
    def __init__(self):
        self.start_time = datetime.now()
        self.cycles = 0
        self.signals_generated = 0
        self.last_signal_time = None
        self.errors = []
        # نماد -> {"direction": "BUY_CALL"/"BUY_PUT", "since": datetime}
        # برای جلوگیری از نوتیفیکیشن تکراری وقتی یه پوزیشن از قبل باز فرض می‌شه،
        # و برای اعمال واقعی CONFIG["max_positions"] (که قبلاً تعریف بود ولی
        # هیچ‌جا استفاده نمی‌شد).
        self.open_positions = {}

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")


state = SystemState()
_modules = {}


def get_module(name):
    if name not in _modules:
        try:
            if name == "collector":
                from collector import collect
                _modules[name] = collect
            elif name == "strategy":
                from strategy import Strategy
                _modules[name] = Strategy
            elif name == "option_selector":
                from option_selector import OptionSelector
                _modules[name] = OptionSelector
            elif name == "signal_generator":
                from signal_generator import generate_signal
                _modules[name] = generate_signal
            elif name == "option_engine":
                from option_engine import OptionEngine, compute_historical_volatility
                _modules[name] = {"engine": OptionEngine, "hv": compute_historical_volatility}
            elif name == "queue_surge":
                import queue_surge
                _modules[name] = queue_surge
            elif name == "fog_meter":
                from fog_meter import measure
                _modules[name] = measure
            elif name == "tape_reader":
                import tape_reader
                _modules[name] = tape_reader
            elif name == "wiv":
                from wiv import WIVCalculator
                _modules[name] = WIVCalculator
            elif name == "index_feed":
                from index_feed import fetch_and_save_indices
                _modules[name] = fetch_and_save_indices
            elif name == "money_flow":
                from money_flow import fetch_and_save_money_flow
                _modules[name] = fetch_and_save_money_flow
            elif name == "dashboard":
                import dashboard
                _modules[name] = dashboard
            elif name == "telegram":
                from telegram_notify import send_telegram_message
                _modules[name] = send_telegram_message
            elif name == "desktop":
                from desktop_notify import send_desktop_notification
                _modules[name] = send_desktop_notification
            elif name == "learning":
                import learning_core
                _modules[name] = learning_core
            elif name == "database":
                from database import create_database
                _modules[name] = create_database
            elif name == "volume":
                from volume_analysis import VolumeAnalysis, PutCallRatio, OpenInterestAnalysis
                _modules[name] = {"vol": VolumeAnalysis, "pcr": PutCallRatio, "oi": OpenInterestAnalysis}
            else:
                _modules[name] = None
        except Exception as e:
            state.log(f"ماژول {name} بارگذاری نشد: {e}", "WARN")
            _modules[name] = None
    return _modules[name]


def collect_market_data(symbol_config):
    name = symbol_config["name"]
    db = symbol_config["db"]
    state.log(f"📊 شروع جمع‌آوری دیتا: {name}")
    data = {"name": name, "db": db, "timestamp": datetime.now().isoformat(), "stock": {}, "options": {}, "market": {}, "indicators": {}}

    try:
        collector = get_module("collector")
        if collector:
            collector()
            state.log(f"  ✅ قیمت سهم دریافت شد")
    except Exception as e:
        state.log(f"  ❌ خطا قیمت سهم: {e}", "ERROR")

    # اکتشافی -- تازه ساخته شده، هنوز روی داده‌ی زنده تست نشده. اگه فیلدها
    # اشتباه بود، فقط لاگ می‌کنه و ادامه می‌ده، به بقیه‌ی تحلیل آسیب نمی‌زنه.
    try:
        from order_book import collect_order_book
        ob = collect_order_book(db)
        data["market"]["order_book"] = ob
        if ob:
            state.log(
                f"  ℹ️ عمق سفارش (اکتشافی): بایاس {ob['pressure']} ({ob['imbalance_pct']}%) | "
                f"اسپرد {ob['spread_pct']}%"
            )
        else:
            state.log("  ⚠️ عمق سفارش دریافت نشد (فیلدهای TSETMC رو چک کن)", "WARN")
    except Exception as e:
        state.log(f"  ⚠️ خطا عمق سفارش: {e}", "WARN")

    # اکتشافی -- تازه ساخته شده. اگه خبر جدید (کدال یا ناظر بازار) پیدا بشه،
    # بلافاصله هشدار می‌ده -- نه فقط لاگ -- چون این نوع خبر می‌تونه قیمت رو
    # ناگهانی جابه‌جا کنه.
    try:
        from daily_news import check_daily_news
        news_items = check_daily_news(db)
        data["market"]["news"] = news_items
        for it in news_items:
            cat = it.get("category", "")
            state.log(f"  📰 خبر جدید [{it['source']}/{cat}]: {it['title']}")
            send_notification(
                {"type": "NEWS", "message": f"📰 خبر جدید ({name})\n\nمنبع: {it['source']} | دسته: {cat}\n{it['title']}"},
                name,
            )
        from news_impact import update_news_impact
        update_news_impact(db)
    except Exception as e:
        state.log(f"  ⚠️ خطا اخبار روزانه: {e}", "WARN")

    try:
        from option_collector import collect_options
        collect_options()
        state.log(f"  ✅ اطلاعات آپشن دریافت شد")
    except Exception as e:
        state.log(f"  ⚠️ خطا آپشن: {e}", "WARN")

    try:
        index_feed = get_module("index_feed")
        if index_feed:
            indices = index_feed()
            data["market"]["indices"] = indices
            state.log(f"  ✅ شاخص‌ها دریافت شد")
    except Exception as e:
        state.log(f"  ⚠️ خطا شاخص: {e}", "WARN")

    try:
        money_flow = get_module("money_flow")
        if money_flow:
            flow = money_flow()
            data["market"]["money_flow"] = flow
            state.log(f"  ✅ جریان پول دریافت شد")
    except Exception as e:
        state.log(f"  ⚠️ خطا جریان پول: {e}", "WARN")

    try:
        hv_func = get_module("option_engine")["hv"]
        hv = hv_func(db)
        data["stock"]["hv"] = hv
        if hv:
            state.log(f"  ✅ نوسان تاریخی: {round(hv*100,1)}%")
    except Exception as e:
        state.log(f"  ⚠️ خطا HV: {e}", "WARN")

    return data


def analyze_technicals(symbol_config):
    name = symbol_config["name"]
    db = symbol_config["db"]
    state.log(f"📈 تحلیل تکنیکال: {name}")
    result = {"action": "WATCH", "confidence": 0, "score": 0, "price": 0, "indicators": {}, "reasons": []}

    try:
        Strategy = get_module("strategy")
        if Strategy:
            strategy = Strategy(db_path=db)
            analysis = strategy.analyze()
            strategy.close()
            if analysis:
                action, confidence, score, price = analysis
                result["action"] = action
                result["confidence"] = confidence
                result["score"] = score
                result["price"] = price
                state.log(f"  ✅ نتیجه: {action} | امتیاز: {score} | اطمینان: {confidence}%")
            else:
                state.log(f"  ⚠️ داده کافی نیست", "WARN")
    except Exception as e:
        state.log(f"  ❌ خطا تحلیل: {e}", "ERROR")

    if result["price"] <= 0 and result["action"] != "WATCH":
        state.log(f"  ⚠️ قیمت نامعتبر ({result['price']}) با اکشن {result['action']} -> اجباری WATCH", "WARN")
        result["action"] = "WATCH"

    return result


def analyze_options(symbol_config, stock_action, stock_confidence, stock_price):
    name = symbol_config["name"]
    db = symbol_config["db"]
    state.log(f"🎯 تحلیل آپشن: {name}")
    result = {"selected": None, "wiv": None, "fog": None, "tape": None,
               "volume_analysis": None, "gamma_exposure": None, "iv_rank": None}

    try:
        OptionSelector = get_module("option_selector")
        if OptionSelector:
            selector = OptionSelector(db_path=db)
            option = selector.run(stock_action=stock_action, stock_confidence=stock_confidence, current_stock_price=stock_price)
            selector.close()
            if option:
                result["selected"] = option
                state.log(f"  ✅ آپشن انتخاب شد: {option.get('symbol')}")
            else:
                state.log(f"  ⚠️ آپشن مناسب پیدا نشد", "WARN")
    except Exception as e:
        state.log(f"  ❌ خطا انتخاب آپشن: {e}", "ERROR")

    # اکتشافی -- فقط اطلاعاتی؛ روی امتیاز/تصمیم BUY-SELL هیچ اثری نداره.
    if _HAS_GAMMA:
        try:
            gx = analyze_gamma_exposure(db, stock_price=stock_price)
            result["gamma_exposure"] = gx
            if gx.get("gamma_wall"):
                state.log(
                    f"  ℹ️ گاما (اکتشافی): دیواره {gx['gamma_wall']:,.0f} | "
                    f"بایاس {gx['regime_bias']} ({gx.get('bias_pct')}%) | "
                    f"اطمینان {gx['confidence']}"
                )
                sel = result.get("selected")
                if sel and sel.get("strike_price"):
                    try:
                        dist = abs(float(sel["strike_price"]) - gx["gamma_wall"]) / gx["gamma_wall"] * 100
                        if dist < 3 and gx["confidence"] != "LOW":
                            sel.setdefault("reasons", []).append(
                                f"⚠️ نزدیک دیواره‌ی گاما ({gx['gamma_wall']:,.0f}) -- احتمال محدودشدن نوسان (اکتشافی)"
                            )
                    except Exception:
                        pass
        except Exception as e:
            state.log(f"  ⚠️ خطا گاما اکسپوژر: {e}", "WARN")

    # اکتشافی -- IV امروز نسبت به تاریخچه‌ی خودش (نه نسبت به HV مثل fog_meter).
    # روی امتیاز/تصمیم اثر نمی‌ذاره تا وقتی حداقل چند هفته داده جمع بشه.
    if _HAS_IVRANK:
        try:
            sel = result.get("selected")
            cur_iv = sel.get("implied_volatility") if sel else None
            if cur_iv:
                record_daily_iv(db, cur_iv)
            ivr = compute_iv_rank_percentile(db, current_iv=cur_iv)
            result["iv_rank"] = ivr
            if ivr["ready"]:
                state.log(
                    f"  ℹ️ IV Rank (اکتشافی): {ivr['iv_rank']}% | "
                    f"IV Percentile: {ivr['iv_percentile']}% | بر پایه‌ی {ivr['days']} روز"
                )
                if sel and ivr["iv_rank"] is not None:
                    if ivr["iv_rank"] >= 80:
                        sel.setdefault("reasons", []).append(
                            f"⚠️ IV Rank بالا ({ivr['iv_rank']}%) -- پرمیوم نسبت به تاریخچه‌ی خودش گرونه (اکتشافی)"
                        )
                    elif ivr["iv_rank"] <= 20:
                        sel.setdefault("reasons", []).append(
                            f"ℹ️ IV Rank پایین ({ivr['iv_rank']}%) -- پرمیوم نسبت به تاریخچه‌ی خودش ارزونه (اکتشافی)"
                        )
            else:
                state.log(f"  ℹ️ IV Rank: داده کافی نیست ({ivr['days']}/{_IV_MIN_DAYS} روز)")
        except Exception as e:
            state.log(f"  ⚠️ خطا IV Rank: {e}", "WARN")

    try:
        WIVCalculator = get_module("wiv")
        if WIVCalculator:
            wiv_calc = WIVCalculator()
            wiv_value = wiv_calc.calculate()
            if wiv_value:
                result["wiv"] = wiv_calc.details
                state.log(f"  ✅ WIV: {wiv_calc.details.get('wiv_pct')}% ({wiv_calc.details.get('wiv_level')})")
    except Exception as e:
        state.log(f"  ⚠️ خطا WIV: {e}", "WARN")

    try:
        fog_measure = get_module("fog_meter")
        if fog_measure:
            price = stock_price or 0
            level, ratio, advice = fog_measure(price, db)
            result["fog"] = {"level": level, "ratio": ratio, "advice": advice}
            state.log(f"  ✅ FOG: {level} ({ratio})")
    except Exception as e:
        state.log(f"  ⚠️ خطا FOG: {e}", "WARN")

    try:
        tape = get_module("tape_reader")
        if tape:
            passed, score, details = tape.evaluate()
            result["tape"] = {"passed": passed, "score": score, "details": details}
            if passed is not None:
                state.log(f"  ✅ TAPE: {score}/5")
    except Exception as e:
        state.log(f"  ⚠️ خطا TAPE: {e}", "WARN")

    # تحلیل حجم
    vol_mod = get_module("volume")
    if vol_mod:
        try:
            vol_analysis = vol_mod["vol"](db)
            vol_signal = vol_analysis.calculate()
            
            pcr = vol_mod["pcr"](db)
            pcr_signal = pcr.calculate()
            
            oi = vol_mod["oi"](db)
            oi_signal = oi.calculate()
            
            result["volume_analysis"] = {
                "volume": vol_signal,
                "put_call": pcr_signal,
                "open_interest": oi_signal,
                "details": vol_analysis.details,
            }
            state.log(f"  ✅ تحلیل حجم: {vol_signal} | Put/Call: {pcr_signal} | OI: {oi_signal}")
        except Exception as e:
            state.log(f"  ⚠️ خطا تحلیل حجم: {e}", "WARN")

    return result


def generate_multi_layer_signal(symbol_config, technicals, options_analysis, market_data):
    name = symbol_config["name"]
    state.log(f"🚦 تولید سیگنال: {name}")

    checks = {
        "technicals_ok": False,
        "volume_ok": True,
        "option_ok": False,
        "wiv_ok": False,
        "fog_ok": False,
        "tape_ok": False,
        "market_ok": False,
    }

    reasons = []
    score = technicals.get("score", 0)

    if technicals["action"] in ("BUY", "STRONG BUY"):
        checks["technicals_ok"] = True
        reasons.append("✅ تحلیل تکنیکال: صعودی")
    elif technicals["action"] in ("SELL", "STRONG SELL"):
        checks["technicals_ok"] = True
        reasons.append("✅ تحلیل تکنیکال: نزولی")
    else:
        reasons.append("❌ تحلیل تکنیکال: خنثی")

    if technicals.get("confidence", 0) >= 40:
        checks["volume_ok"] = True
        reasons.append("✅ حجم: تأیید")

    option = options_analysis.get("selected")
    if option:
        checks["option_ok"] = True
        reasons.append(f"✅ آپشن: {option.get('symbol')}")
    else:
        reasons.append("❌ آپشن: نامناسب")

    wiv_data = options_analysis.get("wiv")
    if wiv_data:
        wiv_level = wiv_data.get("wiv_level", "UNKNOWN")
        wiv_pct = wiv_data.get("wiv_pct", 100)
        if wiv_pct <= CONFIG["max_wiv_for_buy"]:
            checks["wiv_ok"] = True
            reasons.append(f"✅ WIV: {wiv_pct}% ({wiv_level})")
        else:
            reasons.append(f"❌ WIV: {wiv_pct}% (گران)")

    fog_data = options_analysis.get("fog")
    if fog_data:
        fog_level = fog_data.get("level", "UNKNOWN")
        if fog_level in ("CLEAN", "LIGHT"):
            checks["fog_ok"] = True
            reasons.append(f"✅ FOG: {fog_level}")
        else:
            reasons.append(f"❌ FOG: {fog_level}")

    tape_data = options_analysis.get("tape")
    if tape_data:
        if tape_data.get("passed"):
            checks["tape_ok"] = True
            reasons.append(f"✅ TAPE: {tape_data.get('score')}/5")
        else:
            reasons.append(f"⚠️ TAPE: {tape_data.get('score')}/5")

    # بررسی تحلیل حجم
    vol_data = options_analysis.get("volume_analysis")
    if vol_data:
        vol_final = vol_data.get("volume", "NEUTRAL")
        if vol_final == "BUY":
            checks["volume_ok"] = True
            reasons.append(f"✅ حجم: صعودی")
        elif vol_final == "SELL":
            reasons.append(f"❌ حجم: نزولی")
        else:
            reasons.append(f"⚠️ حجم: خنثی")

    indices = market_data.get("indices")
    money_flow = market_data.get("money_flow")
    if indices or money_flow:
        checks["market_ok"] = True
        reasons.append("✅ فضای بازار: بررسی شد")

    passed_checks = sum(1 for v in checks.values() if v)
    total_checks = len(checks)
    check_score = (passed_checks / total_checks) * 100
    final_score = (score * 0.6) + (check_score * 0.4)

    ml_reason = None
    if _HAS_ML and option:
        try:
            db_path = symbol_config.get("db")
            ml_adj, ml_reason = ml_adjust.get_ml_adjustment(option, final_score, db_path)
            if ml_adj:
                final_score = max(0.0, min(100.0, final_score + ml_adj))
                reasons.append(f"🧠 {ml_reason}")
        except Exception as e:
            state.log(f"  ⚠️ خطا تعدیل ML: {e}", "WARN")

    min_checks = 3

    if passed_checks >= min_checks and final_score >= CONFIG["min_score"]:
        if technicals["action"] in ("BUY", "STRONG BUY"):
            signal_type = "BUY_CALL"
        elif technicals["action"] in ("SELL", "STRONG SELL"):
            signal_type = "BUY_PUT"
        else:
            signal_type = "WATCH"
    else:
        signal_type = "WATCH"

    display_score = max(0, round(final_score))  # فقط برای نمایش؛ تصمیم BUY/WATCH بالاتر با مقدار خام گرفته شده

    signal = {
        "type": signal_type,
        "score": display_score,
        "checks_passed": passed_checks,
        "checks_total": total_checks,
        "reasons": reasons,
        "option": option,
        "timestamp": datetime.now().isoformat(),
    }

    if signal_type in ("BUY_CALL", "BUY_PUT") and option:
        targets = _calculate_targets(option, signal_type)
        signal["targets"] = targets
        signal["message"] = _format_signal_message(signal, name)
    else:
        signal["message"] = f"\n{name}: {signal_type} (امتیاز: {display_score})\n"

    state.log(f"  نتیجه: {signal_type} | امتیاز: {display_score} | شرایط: {passed_checks}/{total_checks}")

    return signal


def _calculate_targets(option, signal_type):
    entry = float(option.get("option_price", 0))
    dte = int(option.get("days_to_expire", 30))
    if entry <= 0:
        return None
    if dte <= 7:
        sl_pct = 0.10
    elif dte <= 21:
        sl_pct = 0.12
    else:
        sl_pct = 0.15
    t1_pct = 0.15
    t2_pct = 0.30
    return {
        "entry": round(entry),
        "stop_loss": round(entry * (1 - sl_pct)),
        "stop_loss_pct": round(sl_pct * 100),
        "target1": round(entry * (1 + t1_pct)),
        "target1_pct": round(t1_pct * 100),
        "target2": round(entry * (1 + t2_pct)),
        "target2_pct": round(t2_pct * 100),
    }


def _format_signal_message(signal, symbol_name):
    option = signal.get("option", {})
    targets = signal.get("targets", {})
    lines = []
    lines.append("╔" + "═" * 46 + "╗")
    if signal["type"] == "BUY_CALL":
        lines.append("║" + "  🟢  سیگنال خرید کال  ".center(40) + "║")
    else:
        lines.append("║" + "  🔴  سیگنال خرید پوت  ".center(40) + "║")
    lines.append("╚" + "═" * 46 + "╝")
    lines.append("")
    lines.append(f"📊 نماد: {symbol_name}")
    lines.append(f"📈 امتیاز: {signal['score']}/100")
    lines.append(f"✅ شرایط: {signal['checks_passed']}/{signal['checks_total']}")
    lines.append("")
    if option:
        lines.append(f"🎯 قرارداد: {option.get('symbol')}")
        lines.append(f"   نوع: {option.get('option_type')}")
        lines.append(f"   قیمت اعمال: {option.get('strike_price'):,}")
        lines.append(f"   سررسید: {option.get('expire_date')} ({option.get('days_to_expire')} روز)")
        lines.append(f"   قیمت آپشن: {option.get('option_price'):,}")
        lines.append(f"   دلتا: {option.get('delta')}")
        lines.append("")
    if targets:
        lines.append(f"🛑 حد ضرر: {targets['stop_loss']:,} (-{targets['stop_loss_pct']}%)")
        lines.append(f"🎯 هدف اول: {targets['target1']:,} (+{targets['target1_pct']}%)")
        lines.append(f"🚀 هدف دوم: {targets['target2']:,} (+{targets['target2_pct']}%)")
        lines.append("")
    lines.append("📋 دلایل:")
    for reason in signal.get("reasons", []):
        lines.append(f"   {reason}")
    lines.append("")
    lines.append("━" * 46)
    return "\n".join(lines)


def send_notification(signal, symbol_name):
    if signal["type"] == "WATCH":
        return
    message = signal.get("message", "")
    title = f"AHRAM AI - {signal['type']} {symbol_name}"
    if CONFIG["telegram_enabled"]:
        try:
            telegram = get_module("telegram")
            if telegram:
                ok = telegram(f"{title}\n\n{message}")
                if ok:
                    state.log("  ✅ تلگرام ارسال شد")
                else:
                    state.log("  ⚠️ تلگرام ارسال نشد (بدون پاسخ موفق از سرور)", "WARN")
        except Exception as e:
            state.log(f"  ❌ خطا تلگرام: {e}", "ERROR")
    if CONFIG["desktop_enabled"]:
        try:
            desktop = get_module("desktop")
            if desktop:
                ok = desktop(title, message[:200])
                if ok:
                    state.log("  ✅ دسکتاپ ارسال شد")
                else:
                    state.log("  ⚠️ دسکتاپ ارسال نشد", "WARN")
        except Exception as e:
            state.log(f"  ❌ خطا دسکتاپ: {e}", "ERROR")


def log_signal_to_db(signal, symbol_name, db_name):
    """ذخیره تمام سیگنال‌ها (BUY و WATCH) در دیتابیس"""
    try:
        conn = sqlite3.connect(db_name)
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT,
                symbol TEXT,
                signal_type TEXT,
                composite_score REAL,
                option_symbol TEXT,
                option_price REAL,
                strike_price REAL,
                stop_loss REAL,
                target1 REAL,
                target2 REAL,
                outcome TEXT DEFAULT 'PENDING',
                outcome_pct REAL DEFAULT 0,
                details TEXT
            )
        """)
        
        cur.execute("PRAGMA table_info(signal_history)")
        columns = [row[1] for row in cur.fetchall()]
        
        required_columns = {
            "option_symbol": "TEXT",
            "option_price": "REAL",
            "strike_price": "REAL",
            "stop_loss": "REAL",
            "target1": "REAL",
            "target2": "REAL",
            "composite_score": "REAL",
            "signal_type": "TEXT",
            "details": "TEXT",
            "position_id": "TEXT",
        }
        
        for col_name, col_type in required_columns.items():
            if col_name not in columns:
                try:
                    cur.execute(f"ALTER TABLE signal_history ADD COLUMN {col_name} {col_type}")
                except Exception as _e:
                    state.log(f"⚠️ ستون {col_name} اضافه نشد: {_e}", "WARN")
        
        conn.commit()

        option = signal.get("option", {})
        targets = signal.get("targets", {})
        opt_sym = option.get("symbol") if option else None
        direction = signal["type"]

        # position_id: یه پوزیشن واقعی -- تا وقتی برای همین
        # (نماد پایه + قرارداد + جهت) یه ردیف PENDING/T1_HIT باز هست، همون
        # position_id قبلی استفاده می‌شه (یعنی هر بار سیگنال تکرار بشه، به
        # همون معامله وصل می‌مونه، حتی اگه چند روز طول بکشه). به محض اینکه
        # اون پوزیشن WIN/LOSS بشه، اگه همون قرارداد دوباره سیگنال بگیره، یه
        # position_id کاملاً جدید و مستقل می‌گیره.
        position_id = None
        if opt_sym and direction in ("BUY_CALL", "BUY_PUT", "BUY", "STRONG BUY"):
            cur.execute(
                "SELECT position_id FROM signal_history WHERE symbol=? AND option_symbol=? "
                "AND signal_type=? AND outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (symbol_name, opt_sym, direction),
            )
            r = cur.fetchone()
            if r and r[0]:
                position_id = r[0]
            else:
                slug = symbol_name.replace(" ", "")
                position_id = f"{slug}-{opt_sym}-{direction}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        cur.execute("""
            INSERT INTO signal_history 
            (time, symbol, signal_type, composite_score, option_symbol, 
             option_price, strike_price, stop_loss, target1, target2, details, position_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol_name,
            signal["type"],
            signal["score"],
            opt_sym,
            option.get("option_price") if option else None,
            option.get("strike_price") if option else None,
            targets.get("stop_loss") if targets else None,
            targets.get("target1") if targets else None,
            targets.get("target2") if targets else None,
            json.dumps(signal, ensure_ascii=False, default=str),
            position_id,
        ))
        
        conn.commit()
        conn.close()
        state.log(f"  ✅ سیگنال در دیتابیس ذخیره شد")
    except Exception as e:
        state.log(f"  ❌ خطا دیتابیس: {e}", "ERROR")


def check_live_exits_for_symbol(name, db):
    """پوزیشن‌های باز این نماد رو با قیمت لحظه‌ای آپشن مقایسه می‌کنه و اگه به
    هدف/حد ضرر رسیده باشن، بلافاصله هشدار می‌ده (به‌جای اینکه فقط ساکت توی
    دیتابیس آپدیت بشه و کاربر تا سیکل بعدی داشبورد متوجه نشه)."""
    alerts = []
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute(
            "SELECT position_id, option_symbol, option_price, stop_loss, target1, target2, outcome, MIN(id) "
            "FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') "
            "AND position_id IS NOT NULL GROUP BY position_id"
        )
        rows = cur.fetchall()
        for pos_id, sym, entry, sl, t1, t2, outcome, _min_id in rows:
            entry_f = float(entry) if entry else 0
            if entry_f <= 0:
                continue
            cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (sym,))
            pr = cur.fetchone()
            if not pr or not pr[0]:
                continue
            cur_price = float(pr[0])
            sl_f = float(sl) if sl else None
            t1_f = float(t1) if t1 else None
            t2_f = float(t2) if t2 else None

            new_outcome = None
            if sl_f and cur_price <= sl_f:
                new_outcome = "LOSS"
            elif t2_f and cur_price >= t2_f:
                new_outcome = "WIN"
            elif t1_f and cur_price >= t1_f and outcome == "PENDING":
                new_outcome = "T1_HIT"

            if new_outcome and new_outcome != outcome:
                pct = round(((cur_price - entry_f) / entry_f) * 100, 1)
                # همه‌ی ردیف‌های همین position_id با هم بسته می‌شن -- یه
                # معامله‌ست، نه چندتا -- وگرنه چندین هشدار تکراری فرستاده می‌شه
                cur.execute(
                    "UPDATE signal_history SET outcome=?, outcome_pct=? "
                    "WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                    (new_outcome, pct, pos_id),
                )
                alerts.append((sym, new_outcome, pct, cur_price))
        conn.commit()
        conn.close()
    except Exception as e:
        state.log(f"  ⚠️ خطا بررسی خروج زنده: {e}", "WARN")
        return

    for sym, new_outcome, pct, cur_price in alerts:
        label = {"WIN": "🎯 رسیدن به هدف نهایی", "LOSS": "🛑 برخورد به حد ضرر",
                  "T1_HIT": "✅ رسیدن به هدف اول"}.get(new_outcome, new_outcome)
        state.log(f"  {label}: {sym} ({pct:+}%)")
        msg = f"{label}\n\nنماد: {name}\nقرارداد: {sym}\nقیمت فعلی: {cur_price:,.0f}\nسود/زیان: {pct:+}%"
        send_notification({"type": "EXIT", "message": msg}, name)


def analyze_symbol(symbol_config):
    name = symbol_config["name"]
    db = symbol_config["db"]
    state.log(f"\n{'#' * 60}")
    state.log(f"# {name}")
    state.log(f"{'#' * 60}")

    import config
    config.UNDERLYING = name
    config.DATABASE_NAME = db
    config.INS_CODE = symbol_config["ins_code"]
    config.OPTION_ROOT = symbol_config.get("option_root", "")

    if _HAS_ML:
        try:
            if ml_adjust.needs_daily_update(db):
                result = ml_adjust.train_model(db)
                state.log(f"  🧠 آموزش مدل: {result.get('message', result)}")
        except Exception as e:
            state.log(f"  ⚠️ خطا آموزش مدل: {e}", "WARN")

    market_data = collect_market_data(symbol_config)
    check_live_exits_for_symbol(name, db)
    technicals = analyze_technicals(symbol_config)
    options_analysis = analyze_options(symbol_config, technicals["action"], technicals["confidence"], technicals["price"])
    signal = generate_multi_layer_signal(symbol_config, technicals, options_analysis, market_data.get("market", {}))

    # ✅ ذخیره تمام سیگنال‌ها (BUY و WATCH) — این رفتار قبلی دست‌نخورده می‌مونه،
    # چون گزارش روزانه به رکورد هر سیکل (چه BUY چه WATCH) نیاز داره.
    log_signal_to_db(signal, name, db)

    if signal["type"] != "WATCH":
        direction = signal["type"]
        existing = state.open_positions.get(name)
        max_hold = timedelta(hours=CONFIG.get("max_position_hold_hours", 3))
        still_open = (
            existing is not None
            and existing["direction"] == direction
            and (datetime.now() - existing["since"]) < max_hold
        )

        if still_open:
            state.log(
                f"  ℹ️ سیگنال {direction} تکراریه (پوزیشن از {existing['since'].strftime('%H:%M')} "
                f"باز فرض می‌شه) -> نوتیفیکیشن دوباره ارسال نشد", "INFO"
            )
        elif name not in state.open_positions and len(state.open_positions) >= CONFIG["max_positions"]:
            state.log(
                f"  ⚠️ به سقف {CONFIG['max_positions']} پوزیشن هم‌زمان رسیدیم -> "
                f"نوتیفیکیشن {direction} برای {name} ارسال نشد", "WARN"
            )
        else:
            state.open_positions[name] = {"direction": direction, "since": datetime.now()}
            send_notification(signal, name)
            state.signals_generated += 1
            state.last_signal_time = datetime.now()
    else:
        # برگشتن به WATCH یعنی شرایط فنی/آپشن دیگه پابرجا نیست -> پوزیشن قبلی آزاد می‌شه
        if name in state.open_positions:
            state.log(f"  ℹ️ شرایط {name} به WATCH برگشت -> پوزیشن باز قبلی آزاد شد", "INFO")
            del state.open_positions[name]

    print(signal.get("message", f"\n{name}: {signal['type']} (امتیاز: {signal['score']})"))
    print()

    return signal


def run_cycle():
    state.cycles += 1
    print("\n" + "=" * 60)
    print(f"🔄 سیکل #{state.cycles} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    signals = []
    for sym in CONFIG["symbols"]:
        try:
            signal = analyze_symbol(sym)
            signals.append(signal)
        except Exception as e:
            state.log(f"❌ خطا در تحلیل {sym['name']}: {e}", "ERROR")

    if CONFIG["dashboard_enabled"]:
        try:
            dash = get_module("dashboard")
            if dash:
                dash.generate()
                state.log("📊 داشبورد بروزرسانی شد")
        except Exception as e:
            state.log(f"⚠️ خطا داشبورد: {e}", "WARN")

    return signals


def market_is_open():
    now = datetime.now()
    if now.weekday() in (3, 4):
        return False
    return CONFIG["market_open"] <= now.time() <= CONFIG["market_close"]


def run():
    print("╔" + "═" * 58 + "╗")
    print("║" + "  AHRAM AI PRO v4.1  ".center(58) + "║")
    print("║" + "  سیستم معامله‌گری تجمیعی آپشن  ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    print(f"📊 نمادها: {', '.join(s['name'] for s in CONFIG['symbols'])}")
    print(f"⏰ ساعات: {CONFIG['market_open']} - {CONFIG['market_close']}")
    print(f"🔄 سیکل: هر {CONFIG['cycle_seconds']} ثانیه")
    print()

    while True:
        try:
            if market_is_open():
                run_cycle()
                state.log(f"\n⏳ سیکل بعدی در {CONFIG['cycle_seconds']} ثانیه...")
                time.sleep(CONFIG["cycle_seconds"])
            else:
                now = datetime.now().strftime("%H:%M")
                print(f"\r[{now}] بازار بسته. در انتظار...", end="", flush=True)
                time.sleep(120)
        except KeyboardInterrupt:
            print("\n\n🛑 سیستم متوقف شد.")
            state.log(f"📊 آمار: {state.cycles} سیکل | {state.signals_generated} سیگنال")
            break
        except Exception as e:
            state.log(f"❌ خطا: {e}", "ERROR")
            time.sleep(30)


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_cycle()
    else:
        run()