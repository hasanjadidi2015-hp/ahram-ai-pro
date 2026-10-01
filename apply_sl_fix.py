# -*- coding: utf-8 -*-
import sys
P = "ahram_pro.py"
b = open(P, "rb").read()
EOL = b"\r\n" if b.count(b"\r\n") > 10 else b"\n"
print("EOL:", EOL)
def rep_once(old, new, tag):
    global b
    n = b.count(old)
    print(tag, "matches:", n)
    if n != 1:
        print("ABORT", tag, n)
        sys.exit(1)
    b = b.replace(old, new, 1)
rep_once(b"def _calculate_targets(option, signal_type, vace_data=None, technicals=None):",
    b"def _calculate_targets(option, signal_type, vace_data=None, technicals=None, sl_floor=0.10):", "DEF")
rep_once(b"targets = _calculate_targets(option, signal_type, vace_data=vace_for_targets, technicals=technicals)",
    b"targets = _calculate_targets(option, signal_type, vace_data=vace_for_targets, technicals=technicals, sl_floor=(0.12 if symbol_config.get('ins_code','').startswith('179') else 0.10))", "CALL")
rep_once(b"            sl_pct = 0.15" + EOL,
    b"            sl_pct = 0.15" + EOL + b"    # SL floor from daily range" + EOL + b"    if sl_pct < sl_floor:" + EOL + b"        sl_pct = sl_floor" + EOL, "INSERT")
open(P, "wb").write(b)
print("OK - all 3 applied")