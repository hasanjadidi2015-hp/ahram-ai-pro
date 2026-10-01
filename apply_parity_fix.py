# apply_parity_fix.py - parity WARN check (ASCII-only, abort-safe)
import sys
PATH = "option_selector.py"
raw = open(PATH, "rb").read()
NL = "\r\n" if b"\r\n" in raw else "\n"
text = raw.decode("utf-8")
print("EOL:", repr(NL))
HELPER = NL.join([
    'def _parity_warn(cur, table_name, latest_time, best, signal_type, ua_price):',
    '    """Put-call parity sanity check vs same-strike mirror. WARN only, never blocks."""',
    '    try:',
    '        if not best or not ua_price:',
    '            return',
    '        strike = best.get("strike_price_clean")',
    '        my_price = best.get("option_price_clean", 0) or 0',
    '        exp = str(best.get("expire_date", ""))',
    '        if not strike or not exp or float(my_price) <= 0:',
    '            return',
    '        if signal_type == "BUY_CALL":',
    '            mirror_types = ("PUT", "put", "P", "\\u0641\\u0631\\u0648\\u0634")',
    '            mine_is_call = True',
    '        elif signal_type == "BUY_PUT":',
    '            mirror_types = ("CALL", "call", "C", "\\u062e\\u0631\\u06cc\\u062f")',
    '            mine_is_call = False',
    '        else:',
    '            return',
    '        ph = ",".join("?" for _ in mirror_types)',
    '        cur.execute(',
    '            "SELECT * FROM " + table_name + " WHERE option_type IN (" + ph + ") AND time = ? AND expire_date = ?",',
    '            tuple(mirror_types) + (latest_time, exp),',
    '        )',
    '        rows = cur.fetchall()',
    '        if not rows:',
    '            cur.execute(',
    '                "SELECT * FROM " + table_name + " WHERE option_type IN (" + ph + ") AND time >= datetime(?, \'-10 minutes\') AND expire_date = ?",',
    '                tuple(mirror_types) + (latest_time, exp),',
    '            )',
    '            rows = cur.fetchall()',
    '        mirror_price = None',
    '        for r in rows or []:',
    '            d = dict(r)',
    '            k = d.get("strike_price", d.get("strike"))',
    '            pr = d.get("option_price") or 0',
    '            try:',
    '                k = float(k)',
    '                pr = float(pr)',
    '            except (TypeError, ValueError):',
    '                continue',
    '            if pr <= 0:',
    '                continue',
    '            if abs(k - float(strike)) < 0.01:',
    '                mirror_price = pr',
    '                break',
    '        if mirror_price is None:',
    '            return',
    '        s = float(ua_price)',
    '        k = float(strike)',
    '        if mine_is_call:',
    '            c = float(my_price)',
    '            p = float(mirror_price)',
    '        else:',
    '            c = float(mirror_price)',
    '            p = float(my_price)',
    '        dev_pct = ((c - p) - (s - k)) / s * 100.0',
    '        best["parity_dev_pct"] = round(dev_pct, 2)',
    '        sym = best.get("symbol", "-")',
    '        if mine_is_call and dev_pct > PARITY_WARN_PCT:',
    '            logger.warning(f"\\u26a0\\ufe0f \\u067e\\u0631\\u06cc\\u062a\\u06cc: \\u06a9\\u0627\\u0644 {sym} \\u0628\\u0647 \\u0627\\u0646\\u062f\\u0627\\u0632\\u0647 {abs(dev_pct):.1f}% \\u06af\\u0631\\u0627\\u0646\\u200c\\u062a\\u0631 \\u0627\\u0632 \\u067e\\u0648\\u062a \\u0647\\u0645\\u200c\\u0633\\u0631\\u0631\\u0633\\u06cc\\u062f \\u0627\\u0633\\u062a")',
    '        elif (not mine_is_call) and dev_pct < -PARITY_WARN_PCT:',
    '            logger.warning(f"\\u26a0\\ufe0f \\u067e\\u0631\\u06cc\\u062a\\u06cc: \\u067e\\u0648\\u062a {sym} \\u0628\\u0647 \\u0627\\u0646\\u062f\\u0627\\u0632\\u0647 {abs(dev_pct):.1f}% \\u06af\\u0631\\u0627\\u0646\\u200c\\u062a\\u0631 \\u0627\\u0632 \\u06a9\\u0627\\u0644 \\u0647\\u0645\\u200c\\u0633\\u0631\\u0631\\u0633\\u06cc\\u062f \\u0627\\u0633\\u062a")',
    '    except Exception:',
    '        return',
])
FIXES = [
    ("def get_best_option",
     "PARITY_WARN_PCT = 1.0" + NL + NL + "def get_best_option"),
    ("            best_option = valid_options[0]",
     "            best_option = valid_options[0]" + NL + "            _parity_warn(cur, table_name, latest_time, best_option, signal_type, ua_price)"),
    ("    return best_option",
     "    return best_option" + NL + NL + HELPER),
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