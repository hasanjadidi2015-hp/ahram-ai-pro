def check_live_exits_for_symbol(name, db):
    """پایش خروج زنده. هر خروج یا هدف فقط با دو قرائت پشت‌سرهم تأیید می‌شود.
    قرائت منفرد (مثل ۲۵۰۰ یا ۳۹۵۰ ثابت) هرگز پوزیشن را نمی‌بندد."""
    alerts = []
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        # ورود، حد ضرر و اهداف از اولین ردیف هر پوزیشن (هدف مبنای معامله است)
        cur.execute(
            "SELECT s.position_id, s.option_symbol, s.option_price, s.stop_loss, s.target1, s.target2, s.outcome "
            "FROM signal_history s "
            "JOIN (SELECT position_id, MIN(id) AS mid FROM signal_history "
            "      WHERE outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL GROUP BY position_id) m "
            "ON s.id = m.mid"
        )
        rows = cur.fetchall()
        for pos_id, sym, entry, sl, t1, t2, outcome in rows:
            entry_f = float(entry) if entry else 0.0
            if entry_f <= 0:
                continue
            cur.execute(
                "SELECT option_price FROM options WHERE symbol=? AND option_price>0 AND price_fresh=1 ORDER BY id DESC LIMIT 2",
                (sym,),
            )
            readings = [float(r[0]) for r in cur.fetchall()]
            if not readings:
                state.log(f"  ⚠️ پایش خروج متوقف: قیمت {sym} در options پیدا نشد (position {pos_id}) -- حد ضرر اجرا نمی‌شه", "WARN")
                continue
            cur_price = readings[0]
            prev_price = readings[1] if len(readings) > 1 else None
            sl_f = float(sl) if sl else None
            t1_f = float(t1) if t1 else None
            t2_f = float(t2) if t2 else None
            pnl_pct = (cur_price - entry_f) / entry_f * 100

            # VACE Break-Even (اگر ماژول موجود باشد)
            if _HAS_VACE_V2 and check_break_even and outcome == "PENDING":
                try:
                    if check_break_even(pnl_pct, be_threshold=8.5) and sl_f and sl_f < entry_f:
                        cur.execute(
                            "UPDATE signal_history SET stop_loss=? WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                            (entry_f, pos_id),
                        )
                        state.log(f"  🔬 VACE Break-Even: {sym} PnL {pnl_pct:.1f}% -> SL به {entry_f:.0f}", "INFO")
                        sl_f = entry_f
                except Exception:
                    pass

            def confirmed(level, side):
                # فقط اگر هر دو قرائت آخر در همان سمت سطح باشند. قرائت قبلی نباشد = تأیید نمی‌شود.
                if prev_price is None:
                    return False
                if side == "below":
                    return cur_price <= level and prev_price <= level
                return cur_price >= level and prev_price >= level

            new_outcome = None
            if sl_f and confirmed(sl_f, "below"):
                # خروج روی حد ضرر: سود (WIN)، سربه‌سر (BREAK_EVEN) یا زیان (LOSS) بر اساس قیمت ورود
                _pnl = (cur_price - entry_f) / entry_f
                if _pnl > 0.001:
                    new_outcome = "WIN"
                elif abs(_pnl) <= 0.001:
                    new_outcome = "BREAK_EVEN"
                else:
                    new_outcome = "LOSS"
            elif sl_f and cur_price <= sl_f:
                state.log(f"  ⚠️ حد ضرر {sym}: قیمت {cur_price} زیر {sl_f} ولی تأیید نشد (قرائت قبلی {prev_price}) -- باز می‌ماند", "WARN")
            elif t2_f and confirmed(t2_f, "above"):
                new_outcome = "WIN"
            elif t1_f and outcome == "PENDING" and confirmed(t1_f, "above"):
                new_outcome = "T1_HIT"

            if new_outcome and new_outcome != outcome:
                pct = round(pnl_pct, 1)
                cur.execute(
                    "UPDATE signal_history SET outcome=?, outcome_pct=?, outcome_time=? "
                    "WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                    (new_outcome, pct, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pos_id),
                )
                alerts.append((sym, new_outcome, pct, cur_price))
        conn.commit()
        conn.close()
    except Exception as e:
        state.log(f"  ⚠️ خطا بررسی خروج زنده: {e}", "WARN")
        return
    for sym, new_outcome, pct, cur_price in alerts:
        label = {"WIN": "🎯 رسیدن به هدف نهایی", "LOSS": "🛑 برخورد به حد ضرر",
                 "BREAK_EVEN": "⚖️ سربه‌سر", "T1_HIT": "✅ رسیدن به هدف اول"}.get(new_outcome, new_outcome)
        state.log(f"  {label}: {sym} ({pct:+}%)")
        msg = f"{label}\n\nنماد: {name}\nقرارداد: {sym}\nقیمت فعلی: {cur_price:,.0f}\nسود/زیان: {pct:+}%"
        send_notification({"type": "EXIT", "message": msg}, name)