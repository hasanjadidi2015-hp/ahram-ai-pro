# apply_phase2_fix.py - 3-question WARNs, reasons only, zero score effect
import sys
PATH = "ahram_pro.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
OLD = "                option.setdefault(\"reasons\", [])" + NL
NEW = OLD + \
"                # ===== Phase 2: 3-question risk WARNs (reasons only, zero score effect) =====" + NL + \
"                try:" + NL + \
"                    _p2_be = option.get(\"break_even\")" + NL + \
"                    _p2_tb = option.get(\"theta_burn_pct\")" + NL + \
"                    _p2_ivr = option.get(\"iv_premium_ratio\")" + NL + \
"                    _p2_vol = option.get(\"volatility_used\")" + NL + \
"                    if _p2_be and stock_price:" + NL + \
"                        _p2_need = abs(float(_p2_be) - float(stock_price)) / float(stock_price) * 100.0" + NL + \
"                        _p2_usual = float(_p2_vol) * (5.0 / 365.0) ** 0.5 * 100.0 if _p2_vol else 0.0" + NL + \
"                        if _p2_usual > 0 and (_p2_need > _p2_usual or _p2_need > 4.0):" + NL + \
"                            _p2_w = f\"[WARN-BE] need {_p2_need:.1f}% (usual {_p2_usual:.1f}%, rail 4.0%)\"" + NL + \
"                            option[\"reasons\"].append(_p2_w)" + NL + \
"                            state.log(f\"  {_p2_w}\", \"WARN\")" + NL + \
"                    if _p2_tb is not None and float(_p2_tb) > 2.0:" + NL + \
"                        _p2_w = f\"[WARN-THETA] burn {float(_p2_tb):.2f}%/day\"" + NL + \
"                        option[\"reasons\"].append(_p2_w)" + NL + \
"                        state.log(f\"  {_p2_w}\", \"WARN\")" + NL + \
"                    if _p2_ivr is not None and float(_p2_ivr) > 1.3:" + NL + \
"                        _p2_w = f\"[WARN-IVP] premium {float(_p2_ivr):.2f}x fair\"" + NL + \
"                        option[\"reasons\"].append(_p2_w)" + NL + \
"                        state.log(f\"  {_p2_w}\", \"WARN\")" + NL + \
"                except Exception as _p2_e:" + NL + \
"                    state.log(f\"  Phase2 WARN skip: {_p2_e}\", \"WARN\")" + NL
n = text.count(OLD)
print(f"FIX 0: matches={n}")
if n != 1:
    print(f"ABORT: anchor found {n} times. No changes written.")
    sys.exit(1)
text = text.replace(OLD, NEW, 1)
open(PATH, "wb").write(text.encode("utf-8"))
print("OK: 1 fix applied.")