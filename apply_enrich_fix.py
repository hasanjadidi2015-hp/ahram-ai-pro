# apply_enrich_fix.py - enrich selected with OptionEngine (ASCII-only, abort-safe)
import sys
PATH = "option_selector.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
BLOCK = NL.join([
    "    if best_option and ua_price:",
    "        # Enrich with OptionEngine analysis (Greeks/IV/break-even).",
    "        # Never blocks selection: failure keeps raw dict with WARN.",
    "        try:",
    "            from option_engine import OptionEngine as _OE, compute_historical_volatility as _HV",
    "            _hv = None",
    "            try:",
    "                _hv = _HV(db_path)",
    "            except Exception:",
    "                _hv = None",
    '            _otype = str(best_option.get("option_type", "")).upper()',
    '            if _otype not in ("CALL", "PUT"):',
    '                _otype = "CALL" if signal_type == "BUY_CALL" else "PUT"',
    "            _an = _OE().analyze(",
    '                ua_price, best_option.get("strike_price_clean"),',
    '                best_option.get("option_price_clean"), best_option.get("dte_clean"),',
    '                _otype, best_option.get("volume", 0), _hv,',
    "            )",
    "            for _k, _v in _an.items():",
    "                best_option.setdefault(_k, _v)",
    "        except Exception as _ee:",
    '            logger.warning(f"enrich failed: {_ee}")',
])
FIXES = [
    ("    return best_option",
     BLOCK + NL + "    return best_option"),
]
for i, (old, new) in enumerate(FIXES):
    n = text.count(old)
    print(f"FIX {i}: matches={n}")
    if n != 1:
        print(f"ABORT: anchor {i} found {n} times. No changes written.")
        sys.exit(1)
for old, new in FIXES:
    text = text.replace(old, new, 1)
open(PATH, "wb").write(text.encode("utf-8"))
print("OK: 1 fix applied.")