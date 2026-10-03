# apply_mlspam_fix.py - train attempt at most once/day/DB (ASCII-only, abort-safe)
import sys
PATH = "ml_adjust.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
FIXES = [
    ("    if len(X) < MIN_SAMPLES:",
     "    if len(X) < MIN_SAMPLES:" + NL +
     '        with open(last_train_file, "w") as f:' + NL +
     '            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))'),
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