# apply_shadow_fix.py - ML shadow mode (ASCII-only, abort-safe)
import sys
PATH = "ahram_pro.py"
BRAIN = chr(0x1F9E0)
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
OLD3 = ("            if ml_adj:" + NL +
        "                final_score = max(0.0, min(100.0, final_score + ml_adj))" + NL +
        "                reasons.append(f\"" + BRAIN + " {ml_reason}\")")
NEW3 = ("            if ml_adj:" + NL +
        "                # SHADOW MODE: record prediction, do NOT touch score (validation phase)." + NL +
        "                reasons.append(f\"[ML-SHADOW] {ml_adj:+.0f}: {ml_reason}\")" + NL +
        "                state.log(f\"  [ML-SHADOW] {ml_adj:+.0f} (no effect): {ml_reason}\")")
n = text.count(OLD3)
print(f"FIX 0: matches={n}")
if n != 1:
    print(f"ABORT: anchor found {n} times. No changes written.")
    sys.exit(1)
text = text.replace(OLD3, NEW3, 1)
open(PATH, "wb").write(text.encode("utf-8"))
print("OK: 1 fix applied.")