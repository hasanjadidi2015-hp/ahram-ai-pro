# apply_entry_fix.py - BE-aware re-rank: penalize expensive premium in selection
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
E1_OLD = '''            valid_options.sort(key=lambda x: x['dist_pct'])
            best_option = valid_options[0]
'''
E1_NEW = '''            # BE-aware re-rank: score 5 nearest by dist + IV-premium penalty.
            try:
                from option_engine import OptionEngine as _OE2, compute_historical_volatility as _HV2
                try:
                    _hv2 = _HV2(db_path)
                except Exception:
                    _hv2 = None
                _otype2 = "CALL" if signal_type == "BUY_CALL" else "PUT"
                _cands = sorted(valid_options, key=lambda x: x['dist_pct'])[:5]
                for _c in _cands:
                    try:
                        _an2 = _OE2().analyze(
                            ua_price, _c.get("strike_price_clean"),
                            _c.get("option_price_clean"), _c.get("dte_clean"),
                            _otype2, _c.get("volume", 0), _hv2,
                        )
                        _ivp2 = _an2.get("iv_premium_ratio")
                        _pen2 = 10.0 * max(0.0, float(_ivp2) - 1.2) if _ivp2 else 0.0
                        _c["_rank_score"] = float(_c["dist_pct"]) + _pen2
                    except Exception:
                        _c["_rank_score"] = float(_c["dist_pct"])
                _cands.sort(key=lambda x: x["_rank_score"])
                best_option = _cands[0]
                logger.info(f"BE-aware pick: {best_option.get('symbol')} score={best_option['_rank_score']:.2f} dist={best_option['dist_pct']:.2f}")
                best_option.pop("_rank_score", None)
            except Exception:
                valid_options.sort(key=lambda x: x['dist_pct'])
                best_option = valid_options[0]
'''
patch("option_selector.py", [(E1_OLD, E1_NEW)])
print("ALL DONE")