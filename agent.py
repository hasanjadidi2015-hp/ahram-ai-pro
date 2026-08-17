# -*- coding: utf-8 -*-
"""AHRAM AGENT - نسخه نهایی"""

import sys, sqlite3, time as _time
from datetime import datetime, time as dtime

try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

import config
from database import create_database
from collector import collect
from strategy import Strategy
from option_selector import OptionSelector
from option_engine import compute_historical_volatility
from signal_generator import generate_signal

try:
    import learning_core
    _HAS_LEARNING = True
except: _HAS_LEARNING = False
try:
    from desktop_notify import send_desktop_notification
    _HAS_DESKTOP = True
except: _HAS_DESKTOP = False
try:
    import dashboard
    _HAS_DASHBOARD = True
except: _HAS_DASHBOARD = False
try:
    from option_collector import collect_options as _fetch_options_light
    from option_collector import UNDERLYING_INFO
    _HAS_UINFO = True
except:
    _fetch_options_light = None
    _HAS_UINFO = False
try:
    from index_feed import fetch_and_save_indices as _fetch_indices
except: _fetch_indices = None
try:
    from money_flow import fetch_and_save_money_flow as _fetch_money_flow
except: _fetch_money_flow = None
try:
    from symbols_utils import resolve_ins_code
    _HAS_RESOLVE = True
except: _HAS_RESOLVE = False
try:
    import queue_surge
    _HAS_QUEUE = True
except:
    _HAS_QUEUE = False
try:
    from wiv import WIVCalculator
    _HAS_WIV = True
except:
    _HAS_WIV = False

TRADING_STYLE = "mixed"
MARKET_OPEN = dtime(9, 0)
MARKET_CLOSE = dtime(12, 30)
CYCLE_SECONDS = 300
MAX_OPEN_POSITIONS = 3


def market_is_open():
    now = datetime.now()
    if now.weekday() in (3, 4):
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def _safe(fn, label):
    try:
        return fn()
    except Exception as e:
        print(f"[{label}] ERROR: {e}")
        return None


def _alert(title, text):
    print(text)
    if _HAS_DESKTOP:
        try:
            send_desktop_notification(title, text[:200])
        except Exception as e:
            print("[DESKTOP] ERROR:", e)
    try:
        from telegram_notify import send_telegram_message
        send_telegram_message(f"{title}\n\n{text[:1500]}")
    except Exception:
        pass


def _volume_confirmation():
    try:
        conn = sqlite3.connect(config.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT time, volume FROM prices ORDER BY id DESC LIMIT 25")
        rows = cur.fetchall()
        conn.close()
        vols = [(str(t or ""), float(v)) for t, v in rows if v and float(v) > 0]
        if len(vols) < 5:
            return 1.0, True, "no data"
        vols_old = list(reversed(vols))
        increments = []
        prev_v, prev_d = None, None
        for t, v in vols_old:
            day = t[:10]
            if prev_v is not None and day == prev_d and v >= prev_v:
                increments.append(v - prev_v)
            prev_v, prev_d = v, day
        if len(increments) < 3:
            return 1.0, True, "intraday not enough"
        current_inc = increments[-1]
        prior = increments[:-1]
        avg_inc = sum(prior) / len(prior) if prior else current_inc
        rvol = current_inc / avg_inc if avg_inc > 0 else 1.0
        if rvol >= 1.5:
            return rvol, True, f"high ({rvol:.1f}x)"
        if rvol < 0.8:
            return rvol, False, f"low ({rvol:.1f}x)"
        return rvol, True, f"normal ({rvol:.1f}x)"
    except Exception as e:
        return 1.0, True, f"error: {e}"


def _analyze_symbol(sym):
    name = sym["name"]
    db = sym.get("db", "ahram_v2.db")

    _safe(create_database, "DB")
    if _HAS_LEARNING:
        _safe(learning_core.daily_update, "LEARN")
    hv = _safe(compute_historical_volatility, "VOL-HIST")
    if hv:
        print(f"[VOL-HIST] {round(hv * 100, 1)}%")
    _safe(collect, "STOCK")
    print("[OPTION] ...")
    if _fetch_options_light:
        _safe(_fetch_options_light, "OPTION")
    indices = _safe(_fetch_indices, "INDEX") if _fetch_indices else None
    money_flow = _safe(_fetch_money_flow, "MONEY") if _fetch_money_flow else None
    if _HAS_LEARNING:
        try:
            for a in learning_core.check_live_exits():
                _alert(f"EXIT ({name})", a["text"])
        except Exception as e:
            print("[EXIT] ERROR:", e)

    queue_surge_buy = False
    if _HAS_QUEUE and _HAS_UINFO:
        try:
            u_price = UNDERLYING_INFO.get("price")
            yday = UNDERLYING_INFO.get("yesterday")
            vol_today = UNDERLYING_INFO.get("volume")
            if u_price and yday and yday > 0:
                avg_vol = queue_surge.compute_avg_daily_volume(20)
                qi = queue_surge.detect_heavy_queue(u_price, yday, vol_today, avg_vol, symbol_name=name)
                print(f"[QUEUE] {qi['reason']}")
                if queue_surge.should_trigger_call_surge(qi):
                    queue_surge_buy = True
                    print("[QUEUE] HEAVY QUEUE -> CALL BUY")
        except Exception as e:
            print("[QUEUE] ERROR:", e)

    stock_action = "WATCH"
    stock_confidence = 0
    stock_score = 0
    price = 0

    if queue_surge_buy:
        stock_action = "BUY"
        stock_confidence = 85
        stock_score = 80
        price = UNDERLYING_INFO.get("price") or 0
        print(f"[QUEUE] BUY call (price {int(price)})")
    else:
        try:
            strategy = Strategy()
            result = strategy.analyze()
            try: strategy.close()
            except: pass
            if result is not None:
                stock_action, stock_confidence, stock_score, price = result
            else:
                print("[STRATEGY] not enough data")
        except Exception as e:
            print("[STRATEGY] ERROR:", e)
        rvol, vol_confirmed, vol_reason = _volume_confirmation()
        print(f"[VOL-CONFIRM] {vol_reason}")
        if stock_action in ("BUY", "SELL", "STRONG BUY", "STRONG SELL"):
            if not vol_confirmed:
                stock_confidence = max(0, stock_confidence - 10)
                print("[VOL-CONFIRM] low vol - less confidence")
            elif rvol >= 1.5:
                stock_confidence = min(100, stock_confidence + 10)

    option_decision = None
    try:
        selector = OptionSelector()
        option_decision = selector.run(stock_action=stock_action, stock_confidence=stock_confidence, current_stock_price=price if price else None)
        selector.close()
    except Exception as e:
        print("[OPTION-SELECTOR] ERROR:", e)
    if queue_surge_buy and option_decision:
        option_decision.setdefault("reasons", []).insert(0, "queue surge")
    if _HAS_LEARNING and option_decision:
        try:
            ml_adj, ml_reason = learning_core.get_ml_adjustment(option_decision)
            if ml_adj != 0 and "confidence" in option_decision:
                old = option_decision["confidence"]
                option_decision["confidence"] = max(0, min(100, old + ml_adj))
                option_decision.setdefault("reasons", []).append(ml_reason)
        except Exception as e:
            print("[ML] ERROR:", e)

    signal = None
    if queue_surge_buy:
        try:
            from spread_strategy import build_spread_signal
            signal = build_spread_signal(price or 0, config.DATABASE_NAME, name, stock_confidence)
            if signal:
                print("[SPREAD] Bull Call Spread built for", name)
        except Exception as e:
            print("[SPREAD] ERROR:", e)
    if signal is None:
        signal = generate_signal(stock_action=stock_action, stock_confidence=stock_confidence, stock_score=stock_score, price=price, option_decision=option_decision, indices=indices, money_flow=money_flow, style=TRADING_STYLE)

    print()
    try:
        from fog_meter import measure as _fog
        _fl, _fr, _fa = _fog(price or 0, config.DATABASE_NAME)
        print("[FOG] %s (ratio %s) - %s" % (_fl, _fr, _fa))
        if signal.get("type") == "BUY":
            _od = signal.get("option_decision") or {}
            _is_spread = _od.get("option_type") == "SPREAD"
            if _fl == "DENSE" and not _is_spread:
                signal["type"] = "WATCH"
                print("[FOG GATE] dense fog + naked -> WATCH (skip)")
            elif _fl in ("DENSE", "FOG"):
                signal["confidence"] = max(0, int(signal.get("confidence", 0) * 0.7))
    except Exception as _e:
        print("[FOG] ERROR:", _e)

    try:
        import tape_reader as _tr
        _tpassed, _tscore, _tdetails = _tr.evaluate()
        if _tpassed is None:
            print("[TAPE] data unavailable - skip gate")
        else:
            print("[TAPE] %d/5 (saraneh=%.0fM, ratio=%.2f, vol=%.1fx)" % (_tscore, _tdetails.get("saraneh_toman",0)/1e6, _tdetails.get("bs_ratio",0), _tdetails.get("vol_ratio",0)))
            if signal.get("type") == "BUY" and not _tpassed and not queue_surge_buy:
                signal["type"] = "WATCH"
                print("[TAPE GATE] weak order book (%d/5) -> WATCH" % _tscore)
    except Exception as _e:
        print("[TAPE] ERROR:", _e)

    if _HAS_WIV:
        try:
            wiv_calc = WIVCalculator()
            wiv_value = wiv_calc.calculate()
            if wiv_value:
                wiv_calc.print_report()
                wiv_signal, wiv_strength, wiv_reason = wiv_calc.get_signal()
                print(f"[WIV] {wiv_signal}: {wiv_reason}")
                if signal.get("type") == "BUY" and wiv_calc.details.get("wiv_level") in ("HIGH", "EXTREME"):
                    print("⚠️ WIV WARNING: آپشن‌ها گران هستند - احتیاط کنید!")
                    signal["confidence"] = max(0, signal.get("confidence", 0) - 10)
                if signal.get("type") == "BUY" and wiv_calc.details.get("wiv_level") == "LOW":
                    print("✅ WIV BONUS: آپشن‌ها ارزان هستند - فرصت مناسب!")
                    signal["confidence"] = min(100, signal.get("confidence", 0) + 5)
        except Exception as _e:
            print(f"[WIV] ERROR: {_e}")

    print(signal["message"])
    print()

    if signal.get("type") == "BUY":
        too_many = False
        if _HAS_LEARNING:
            try:
                conn = sqlite3.connect(config.DATABASE_NAME)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome IN ('PENDING','T1_HIT')")
                if cur.fetchone()[0] >= MAX_OPEN_POSITIONS:
                    too_many = True
                    print("[RISK] max positions")
                conn.close()
            except: pass
        if not too_many:
            if _HAS_LEARNING:
                new_id = _safe(lambda: learning_core.log_signal(signal), "LOG")
                if new_id:
                    _alert(f"BUY ({name})", signal["message"])
            else:
                _alert(f"BUY ({name})", signal["message"])
    return signal


def run_once():
    print("\n" + "=" * 60)
    print("AHRAM AGENT   ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    for sym in config.SYMBOLS:
        name = sym["name"]
        db = sym.get("db", "ahram_v2.db")
        ins = sym.get("ins_code", "")
        if not ins and _HAS_RESOLVE:
            ins = resolve_ins_code(name) or ""
        config.UNDERLYING = name
        if ins:
            config.INS_CODE = ins
        config.DATABASE_NAME = db
        config.OPTION_ROOT = sym.get("option_root", "")
        print(f"\n{'#' * 60}\n# {name}\n{'#' * 60}")
        try:
            _analyze_symbol(sym)
        except Exception as e:
            print(f"[{name}] ERROR:", e)
    if _HAS_DASHBOARD:
        _safe(dashboard.generate, "DASH")


def run_loop():
    print("=" * 60)
    print("AHRAM AGENT - auto")
    print(f"Symbols: {', '.join(s['name'] for s in config.SYMBOLS)}")
    print(f"Hours: {MARKET_OPEN} - {MARKET_CLOSE}")
    print("=" * 60)
    while True:
        try:
            if market_is_open():
                run_once()
                print(f"\nNext in {CYCLE_SECONDS}s...\n")
                _time.sleep(CYCLE_SECONDS)
            else:
                now = datetime.now().strftime("%H:%M")
                print(f"\r[{now}] closed. checking...", end="", flush=True)
                _time.sleep(120)
        except KeyboardInterrupt:
            print("\n\nstopped.")
            break
        except Exception as e:
            print("\nerror:", e)
            _time.sleep(30)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        run_loop()
    else:
        run_once()