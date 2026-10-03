# apply_enrich_fix2.py - fill None keys too (ASCII-only, abort-safe)
import sys
PATH = "option_selector.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
FIXES = [
    ("            for _k, _v in _an.items():" + NL +
     "                best_option.setdefault(_k, _v)",
     "            for _k, _v in _an.items():" + NL +
     "                if _k not in best_option or best_option[_k] is None:" + NL +
     "                    best_option[_k] = _v"),
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