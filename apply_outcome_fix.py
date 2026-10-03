# apply_outcome_fix.py - explicit PENDING on INSERT (ASCII-only, abort-safe)
import sys
PATH = "ahram_pro.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
FIXES = [
    ("target1, target2, details, position_id,",
     "target1, target2, outcome, details, position_id,"),
    ("VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    ('            targets.get("target2") if targets else None,',
     '            targets.get("target2") if targets else None,' + NL + '            "PENDING",'),
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