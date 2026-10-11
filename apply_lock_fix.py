# apply_lock_fix.py - tiered profit-lock + honest stop labels
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
B1_OLD = '''                except Exception as _be_e:
                    pass
'''
B1_NEW = '''                except Exception as _be_e:
                    pass

            # Tiered profit-lock (anti-give-back): ratchet SL up on PENDING + T1_HIT.
            try:
                if outcome in ("PENDING", "T1_HIT"):
                    _lock = None
                    if pnl_pct >= 25.0:
                        _lock = entry_f * 1.15
                    elif pnl_pct >= 15.0:
                        _lock = entry_f * 1.08
                    if _lock is not None and (not sl_f or _lock > sl_f) and _lock < cur_price:
                        cur.execute(
                            "UPDATE signal_history SET stop_loss=? WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                            (_lock, pos_id),
                        )
                        state.log(f"  [LOCK] {sym} PnL {pnl_pct:.1f}% -> SL locked {(_lock / entry_f - 1) * 100:+.0f}%", "INFO")
                        sl_f = _lock
            except Exception:
                pass
'''
B2_OLD = '''            if sl_f and cur_price <= sl_f:
                new_outcome = "LOSS"
'''
B2_NEW = '''            if sl_f and cur_price <= sl_f:
                new_outcome = "LOSS" if pnl_pct < 0 else "WIN"
'''
patch("ahram_pro.py", [(B1_OLD, B1_NEW), (B2_OLD, B2_NEW)])
print("ALL DONE")