# apply_mlfix_fix.py - single-class predict_proba safety
import sys
PATH = "ml_adjust.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
M1_OLD = "        p = model.predict_proba([feats])[0][1]" + NL
M1_NEW = ("        _proba = model.predict_proba([feats])[0]" + NL +
          "        try:" + NL +
          "            p = float(_proba[list(model.classes_).index(1)])" + NL +
          "        except (ValueError, IndexError):" + NL +
          "            p = 0.0" + NL)
n1 = text.count(M1_OLD)
print(f"FIX 0: matches={n1}")
if n1 != 1:
    print(f"ABORT: anchor found {n1} times. No changes written.")
    sys.exit(1)
text = text.replace(M1_OLD, M1_NEW, 1)
open(PATH, "wb").write(text.encode("utf-8"))
print("OK: 1 fix applied.")