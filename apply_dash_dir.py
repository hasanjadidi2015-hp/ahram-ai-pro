# apply_dash_dir.py - direction badge (ASCII-only, abort-safe)
import sys
PATH = "dashboard.py"
FIXES = [
    ("sh.stop_loss, sh.target1, sh.target2",
     "sh.stop_loss, sh.target1, sh.target2, sh.signal_type"),
    ("_, stock, sym, option_price, sl, t1, t2 = entry",
     "_, stock, sym, option_price, sl, t1, t2, direction = entry"),
    ("rows.append((pos_id, stock, sym, option_price, sl, t1, t2, outcome, v2_score, v2_best))",
     "rows.append((pos_id, stock, sym, option_price, sl, t1, t2, direction, outcome, v2_score, v2_best))"),
    ("pos_id, stock, sym, entry, sl, t1, t2, outcome, v2_score, v2_best = row",
     "pos_id, stock, sym, entry, sl, t1, t2, direction, outcome, v2_score, v2_best = row"),
    ('"pct": gain, "outcome": outcome,',
     '"pct": gain, "direction": direction, "outcome": outcome,'),
    ('            pos_rows += f\'\'\'',
     '            direction = (p.get("direction") or "")\n'
     '            if direction == "BUY_PUT":\n'
     '                direction_txt = "\\u062E\\u0631\\u06CC\\u062F PUT"\n'
     '            else:\n'
     '                direction_txt = "\\u062E\\u0631\\u06CC\\u062F CALL"\n'
     '            pos_rows += f\'\'\''),
    ('<span class="pos-sym">{_esc(p["symbol"])}</span>',
     '<span class="pos-sym">{_esc(p["symbol"])}</span>\n'
     '              <span class="pos-dir">{_esc(direction_txt)}</span>'),
    ("grid-template-columns:70px 100px 1fr 1fr 80px 90px",
     "grid-template-columns:70px 100px 90px 1fr 1fr 80px 90px"),
    (".pos-status{{color:var(--text-dim);font-size:12px}}",
     ".pos-status{{color:var(--text-dim);font-size:12px}}\n.pos-dir{{color:var(--accent);font-size:12px;font-weight:700}}"),
]
raw = open(PATH, "rb").read()
text = raw.decode("utf-8")
for i, (old, new) in enumerate(FIXES):
    n = text.count(old)
    print(f"FIX {i}: matches={n}")
    if n != 1:
        print(f"ABORT: anchor {i} found {n} times. No changes written.")
        sys.exit(1)
for old, new in FIXES:
    text = text.replace(old, new, 1)
open(PATH, "wb").write(text.encode("utf-8"))
print("OK: 9 fixes applied.")