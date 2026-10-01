# apply_mlfeat_fix.py - None-safe ML features (ASCII-only, abort-safe)
import sys
PATH = "ml_adjust.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
HELPER = NL.join([
    'def _num(v, default):',
    '    """None-safe float with neutral default (missing value, not dropped row)."""',
    '    try:',
    '        return float(v) if v is not None else default',
    '    except (TypeError, ValueError):',
    '        return default',
])
FIXES = [
    ("def _extract_features(option_decision, score):",
     HELPER + NL + NL + "def _extract_features(option_decision, score):"),
    ("        return [",
     "        od = option_decision or {}" + NL + "        return ["),
    ('            float(option_decision.get("confidence", 50)),' + NL +
     '            float(option_decision.get("delta", 0.5)),' + NL +
     '            float(option_decision.get("iv_premium_ratio", 1.0)),' + NL +
     '            float(option_decision.get("probability_of_profit", 50)),' + NL +
     '            float(option_decision.get("distance_pct", 0)),' + NL +
     '            float(score),',
     '            _num(od.get("confidence", 50), 50),' + NL +
     '            _num(od.get("delta", 0.5), 0.5),' + NL +
     '            _num(od.get("iv_premium_ratio", 1.0), 1.0),' + NL +
     '            _num(od.get("probability_of_profit", 50), 50),' + NL +
     '            _num(od.get("distance_pct", 0), 0),' + NL +
     '            _num(score, 50),'),
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
print("OK: 3 fixes applied.")