# apply_exittime_fix.py - stamp exit time on flips; settled report by exit day
import sys
def patch(path, pairs):
    raw = open(path, "rb").read()
    NL = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8")
    print(path, "EOL:", repr(NL))
    for i, (old, new) in enumerate(pairs):
        old = old.replace("\n", NL)
        new = new.replace("\n", NL)
        n = text.count(old)
        print(f"FIX {i}: matches={n}")
        if n != 1:
            print(f"ABORT: {path} anchor {i} found {n} times. No changes written.")
            sys.exit(1)
        text = text.replace(old, new, 1)
    open(path, "wb").write(text.encode("utf-8"))
    print(f"OK: {len(pairs)} fix(es) applied to {path}.")
A1_OLD = '''            "v2_best_symbol": "TEXT",
        }'''
A1_NEW = '''            "v2_best_symbol": "TEXT",
            "outcome_time": "TEXT",
        }'''
A2_OLD = '''                cur.execute(
                    "UPDATE signal_history SET outcome=?, outcome_pct=? "
                    "WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                    (new_outcome, pct, pos_id),
                )'''
A2_NEW = '''                cur.execute(
                    "UPDATE signal_history SET outcome=?, outcome_pct=?, outcome_time=? "
                    "WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                    (new_outcome, pct, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pos_id),
                )'''
R1_OLD = '''            "SELECT option_symbol, option_price, outcome, outcome_pct, MAX(time) "
            "FROM signal_history WHERE outcome IN ('WIN','LOSS') AND position_id IS NOT NULL "
            "AND time LIKE ? GROUP BY position_id ORDER BY MAX(time)",'''
R1_NEW = '''            "SELECT option_symbol, option_price, outcome, outcome_pct, MAX(outcome_time) "
            "FROM signal_history WHERE outcome IN ('WIN','LOSS') AND position_id IS NOT NULL "
            "AND outcome_time LIKE ? GROUP BY position_id ORDER BY MAX(outcome_time)",'''
patch("ahram_pro.py", [(A1_OLD, A1_NEW), (A2_OLD, A2_NEW)])
patch("report.py", [(R1_OLD, R1_NEW)])
print("ALL DONE")