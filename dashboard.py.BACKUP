# -*- coding: utf-8 -*-
"""AHRAM AI PRO — داشبورد نمایشی یکپارچه (Option Decision System).

تفاوت با dashboard.py:
- نمایش CALL SCORE V2 با breakdown
- نمایش RISK های V2
- نمایش بهترین قرارداد V2
- نمایش IV Rank V2, Greeks V2
- همه فقط نمایش، هیچ منطق سیگنال تغییر نمی‌کنه
"""
import html
import os
import sqlite3
import json
from datetime import datetime

OUTPUT_FILE = "dashboard.html"
OUTPUT_FILE_VIP5 = "options_dashboard_VIP5.html"
REFRESH_SECONDS = 20
SYMBOL_DBS = [
    ("اهرم", "ahram_v2.db"),
    ("وبملت", "webmellt.db"),
    ("شستا", "shasta.db"),
]

def _connect(db):
    try:
        return sqlite3.connect(db) if os.path.exists(db) else None
    except Exception:
        return None

def _safe(cur, sql, args=()):
    try:
        cur.execute(sql, args)
        return cur.fetchall()
    except Exception:
        return []

def _fmt(value, fallback="—"):
    try:
        return f"{int(float(value)):,}"
    except Exception:
        return fallback

def _pct(value):
    try:
        return f"{float(value):+.1f}%"
    except Exception:
        return "—"

def _esc(value):
    return html.escape(str(value or "—"))

def _update_pending_outcomes(cur, conn):
    rows = _safe(
        cur,
        "SELECT position_id, option_symbol, option_price, stop_loss, target1, target2, outcome, MIN(id) "
        "FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') "
        "AND position_id IS NOT NULL GROUP BY position_id",
    )
    changed = False
    for pos_id, sym, entry, sl, t1, t2, outcome, _ in rows:
        try:
            entry_f = float(entry or 0)
            if entry_f <= 0:
                continue
            cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (sym,))
            row = cur.fetchone()
            if not row or not row[0]:
                continue
            current = float(row[0])
            new = None
            if sl and current <= float(sl):
                new = "LOSS"
            elif t2 and current >= float(t2):
                new = "WIN"
            elif t1 and current >= float(t1) and outcome == "PENDING":
                new = "T1_HIT"
            if new and new != outcome:
                gain = round((current - entry_f) / entry_f * 100, 1)
                cur.execute(
                    "UPDATE signal_history SET outcome=?, outcome_pct=? "
                    "WHERE position_id=? AND outcome IN ('PENDING','T1_HIT')",
                    (new, gain, pos_id),
                )
                changed = True
        except Exception:
            continue
    if changed:
        conn.commit()

def _latest_signal(cur):
    # تلاش برای خواندن ستون‌های V2 هم
    try:
        rows = _safe(
            cur,
            "SELECT time, signal_type, composite_score, option_symbol, option_price, strike_price, "
            "stop_loss, target1, target2, details, v2_score, v2_decision, v2_best_symbol "
            "FROM signal_history ORDER BY id DESC LIMIT 1",
        )
        if not rows:
            return {"type": "WAIT", "score": None, "time": None, "option": None, "v2_score": None, "v2_decision": None, "v2_best": None, "details": None}
        t, st, score, sym, op, strike, sl, t1, t2, details, v2_score, v2_dec, v2_best = rows[0]
        return {
            "time": t, "type": (st or "WAIT").upper(), "score": score,
            "option": sym, "option_price": op, "strike": strike,
            "stop": sl, "t1": t1, "t2": t2, "details": details,
            "v2_score": v2_score, "v2_decision": v2_dec, "v2_best": v2_best,
        }
    except Exception:
        rows = _safe(
            cur,
            "SELECT time, signal_type, composite_score, option_symbol, option_price, strike_price, "
            "stop_loss, target1, target2, details FROM signal_history ORDER BY id DESC LIMIT 1",
        )
        if not rows:
            return {"type": "WAIT", "score": None, "time": None, "option": None, "v2_score": None, "v2_decision": None, "v2_best": None, "details": None}
        t, st, score, sym, op, strike, sl, t1, t2, details = rows[0]
        return {
            "time": t, "type": (st or "WAIT").upper(), "score": score,
            "option": sym, "option_price": op, "strike": strike,
            "stop": sl, "t1": t1, "t2": t2, "details": details,
            "v2_score": None, "v2_decision": None, "v2_best": None,
        }

def _symbol_info(name, db):
    info = {
        "name": name, "price": None, "price_time": None,
        "signal": {"type": "WAIT", "score": None, "time": None, "option": None, "v2_score": None, "v2_decision": None, "v2_best": None, "details": None},
        "option_days": None, "option_volume": None,
        "gamma_wall": None, "gamma_regime": None, "gamma_conf": None,
        "advanced_greeks": None, "v2_details": None,
        "order_state": "NO_DATA", "order_pressure": "UNKNOWN", "imbalance": None,
        "spread": None, "news_count": 0, "latest_news": None,
    }
    conn = _connect(db)
    if not conn:
        return info
    cur = conn.cursor()
    try:
        rows = _safe(cur, "SELECT time, last_price FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT 1")
        if rows:
            info["price_time"], info["price"] = rows[0]
        info["signal"] = _latest_signal(cur)
        try:
            details = info["signal"].get("details")
            parsed = json.loads(details) if details else {}
            info["advanced_greeks"] = ((parsed.get("option") or {}).get("advanced_greeks"))
            # V2 details
            v2_dec = parsed.get("v2_decision")
            if v2_dec:
                info["v2_details"] = v2_dec
            else:
                # سعی کن از فیلدهای مستقیم
                if parsed.get("v2_best"):
                    info["v2_details"] = {"best_contract": parsed.get("v2_best"), "final_score": parsed.get("v2_score")}
        except Exception:
            pass
        opt = info["signal"].get("option")
        if opt:
            rows = _safe(cur, "SELECT days_to_expire, volume FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (opt,))
            if rows:
                info["option_days"], info["option_volume"] = rows[0]
        rows = _safe(cur, "SELECT title, category, event_date FROM daily_news ORDER BY id DESC LIMIT 1")
        if rows:
            title, cat, event_date = rows[0]
            info["latest_news"] = {"title": title, "category": cat, "date": event_date}
        rows = _safe(cur, "SELECT COUNT(*) FROM daily_news WHERE event_date=date('now')")
        if rows:
            info["news_count"] = rows[0][0]
        # فیکس باگ 2026-08-31: تشخیص صف خرید/فروش برعکس بود - منطق جدید مثل order_book.py ولی مقاوم به stale
        latest_time_rows = _safe(cur, "SELECT time FROM order_book ORDER BY id DESC LIMIT 1")
        latest_time = latest_time_rows[0][0] if latest_time_rows else None
        if latest_time:
            rows = _safe(cur, "SELECT buy_price, sell_price, buy_volume, sell_volume, buy_count, sell_count FROM order_book WHERE time=? ORDER BY level ASC, id ASC", (latest_time,))
            if not rows:
                rows = _safe(cur, "SELECT buy_price, sell_price, buy_volume, sell_volume, buy_count, sell_count FROM order_book ORDER BY id DESC LIMIT 5")
        else:
            rows = _safe(cur, "SELECT buy_price, sell_price, buy_volume, sell_volume, buy_count, sell_count FROM order_book ORDER BY id DESC LIMIT 5")
        if rows:
            buy_prices = [float(r[0] or 0) for r in rows]
            sell_prices = [float(r[1] or 0) for r in rows]
            buy_vol = sum(float(r[2] or 0) for r in rows)
            sell_vol = sum(float(r[3] or 0) for r in rows)
            buy_cnt = sum(int(float(r[4] or 0)) for r in rows)
            sell_cnt = sum(int(float(r[5] or 0)) for r in rows)
            best_buy = float(rows[0][0] or 0) if rows else 0
            if best_buy == 0:
                best_buy = next((x for x in buy_prices if x > 0), 0)
            best_sell = float(rows[0][1] or 0) if rows else 0
            if best_sell == 0:
                best_sell = next((x for x in sell_prices if x > 0), 0)
            # مقاوم به قیمت stale: اگر حجم و تعداد صفر، طرف خالی است
            buy_side_empty = (buy_vol == 0 and buy_cnt == 0)
            sell_side_empty = (sell_vol == 0 and sell_cnt == 0)
            if best_buy == 0:
                buy_side_empty = buy_side_empty or (buy_vol == 0)
            if best_sell == 0:
                sell_side_empty = sell_side_empty or (sell_vol == 0)
            if buy_side_empty and sell_side_empty:
                info["order_state"] = "NO_DATA"
            elif sell_side_empty and not buy_side_empty:
                info["order_state"] = "LOCKED_BUY_QUEUE"
                info["order_pressure"] = "BUY_QUEUE"
            elif buy_side_empty and not sell_side_empty:
                info["order_state"] = "LOCKED_SELL_QUEUE"
                info["order_pressure"] = "SELL_QUEUE"
            elif buy_vol + sell_vol > 0:
                info["order_state"] = "TWO_SIDED"
                info["imbalance"] = round((buy_vol - sell_vol) / (buy_vol + sell_vol) * 100, 1)
                if best_buy and best_sell >= best_buy:
                    info["spread"] = round((best_sell - best_buy) / best_buy * 100, 3)
                if info["imbalance"] > 20:
                    info["order_pressure"] = "BUY_HEAVY"
                elif info["imbalance"] < -20:
                    info["order_pressure"] = "SELL_HEAVY"
                else:
                    info["order_pressure"] = "BALANCED"
    finally:
        conn.close()
    try:
        from gamma_exposure import analyze_gamma_exposure
        gx = analyze_gamma_exposure(db)
        info["gamma_wall"] = gx.get("gamma_wall")
        info["gamma_regime"] = gx.get("regime_bias")
        info["gamma_conf"] = gx.get("confidence")
    except Exception:
        pass
    return info

def _latest_max_pain(db):
    conn = _connect(db)
    if not conn:
        return []
    cur = conn.cursor()
    rows = _safe(
        cur,
        "SELECT expiry, stock_price, max_pain_strike, current_distance_pct, "
        "data_quality FROM max_pain_history ORDER BY id DESC LIMIT 3",
    )
    conn.close()
    return rows

def _open_positions():
    output = []
    for name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        _update_pending_outcomes(cur, conn)
        # نکته‌ی مهم: نمی‌شه چند تا MIN/MAX مختلف (MIN(id) و MAX(v2_score) و
        # MAX(v2_best_symbol)) رو تو یه SELECT با ستون‌های خام (option_price,
        # stop_loss, ...) قاطی کرد -- رفتار SQLite برای اینکه ستون خام از کدوم
        # ردیف بیاد فقط وقتی یه MIN/MAX تنها تو کوئری باشه مشخصه؛ با چندتا
        # MIN/MAX، انتخاب ردیف برای ستون‌های خام مبهم می‌شه (همون چیزی که باعث
        # شد قیمت ورود اشتباه نشون داده بشه). این‌جا با دو زیرکوئری صریح --
        # یکی برای ردیف اولین ثبت (قیمت ورود واقعی)، یکی برای آخرین وضعیت --
        # این ابهام کاملاً برطرف می‌شه.
        entry_rows = _safe(
            cur,
            """
            SELECT sh.position_id, sh.symbol, sh.option_symbol, sh.option_price,
                   sh.stop_loss, sh.target1, sh.target2
            FROM signal_history sh
            INNER JOIN (
                SELECT position_id, MIN(id) AS entry_id
                FROM signal_history
                WHERE position_id IS NOT NULL
                GROUP BY position_id
            ) first_row ON sh.id = first_row.entry_id
            """,
        )
        entry_by_pos = {r[0]: r for r in (entry_rows or [])}

        latest_rows = _safe(
            cur,
            """
            SELECT sh.position_id, sh.outcome, sh.v2_score, sh.v2_best_symbol
            FROM signal_history sh
            INNER JOIN (
                SELECT position_id, MAX(id) AS latest_id
                FROM signal_history
                WHERE position_id IS NOT NULL
                GROUP BY position_id
            ) last_row ON sh.id = last_row.latest_id
            """,
        )
        # fallback اگر ستون‌های v2 نباشن
        if not latest_rows:
            latest_rows = _safe(
                cur,
                """
                SELECT sh.position_id, sh.outcome, NULL, NULL
                FROM signal_history sh
                INNER JOIN (
                    SELECT position_id, MAX(id) AS latest_id
                    FROM signal_history
                    WHERE position_id IS NOT NULL
                    GROUP BY position_id
                ) last_row ON sh.id = last_row.latest_id
                """,
            )
        latest_by_pos = {r[0]: r for r in (latest_rows or [])}

        rows = []
        for pos_id, latest in latest_by_pos.items():
            _, outcome, v2_score, v2_best = latest
            if outcome not in ("PENDING", "T1_HIT"):
                continue
            entry = entry_by_pos.get(pos_id)
            if not entry:
                continue
            _, stock, sym, option_price, sl, t1, t2 = entry
            rows.append((pos_id, stock, sym, option_price, sl, t1, t2, outcome, v2_score, v2_best))
        for row in rows:
            pos_id, stock, sym, entry, sl, t1, t2, outcome, v2_score, v2_best = row
            current = entry
            price_rows = _safe(cur, "SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (sym,))
            if price_rows and price_rows[0][0]:
                current = price_rows[0][0]
            try:
                gain = round((float(current) - float(entry)) / float(entry) * 100, 1)
            except Exception:
                gain = 0
            output.append({
                "id": pos_id, "stock": stock or name, "symbol": sym,
                "entry": entry, "current": current, "stop": sl, "t1": t1, "t2": t2,
                "pct": gain, "outcome": outcome, "v2_score": v2_score, "v2_best": v2_best,
            })
        conn.close()
    return output

def _all_signals(limit=12):
    all_rows = []
    for _, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        try:
            rows = _safe(
                cur,
                "SELECT time, symbol, signal_type, composite_score, option_symbol, outcome, outcome_pct, v2_score, v2_decision "
                "FROM signal_history ORDER BY id DESC LIMIT 20",
            )
            all_rows.extend(rows)
        except Exception:
            rows = _safe(
                cur,
                "SELECT time, symbol, signal_type, composite_score, option_symbol, outcome, outcome_pct "
                "FROM signal_history ORDER BY id DESC LIMIT 20",
            )
            # pad
            rows = [r + (None, None) for r in rows]
            all_rows.extend(rows)
        conn.close()
    all_rows.sort(key=lambda x: x[0] or "", reverse=True)
    return all_rows[:limit]

def _recent_news(limit=5):
    result = []
    for name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        rows = _safe(cur, "SELECT time, source, title, category, event_date FROM daily_news ORDER BY id DESC LIMIT 5")
        for t, source, title, cat, event_date in rows:
            result.append((t, name, source, title, cat, event_date))
        conn.close()
    result.sort(key=lambda x: x[0] or "", reverse=True)
    return result[:limit]

def _ai_stats():
    wins = losses = pending = total = 0
    for _, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        for sql, target in [
            ("SELECT COUNT(DISTINCT position_id) FROM signal_history WHERE outcome='WIN'", "wins"),
            ("SELECT COUNT(DISTINCT position_id) FROM signal_history WHERE outcome='LOSS'", "losses"),
            ("SELECT COUNT(DISTINCT position_id) FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL", "pending"),
            ("SELECT COUNT(*) FROM signal_history", "total"),
        ]:
            rows = _safe(cur, sql)
            value = rows[0][0] if rows else 0
            if target == "wins": wins += value
            elif target == "losses": losses += value
            elif target == "pending": pending += value
            else: total += value
        conn.close()
    rate = round(wins / (wins + losses) * 100, 1) if wins + losses else 0
    return wins, losses, pending, total, rate

def _sig_meta(signal_type):
    key = (signal_type or "WAIT").upper()
    mapping = {
        "BUY": ("buy", "خرید"), "STRONG BUY": ("buy", "خرید قوی"),
        "BUY_CALL": ("buy", "خرید کال"), "BUY_PUT": ("sell", "خرید پوت"),
        "WATCH": ("watch", "تحت نظر"), "WAIT": ("muted", "صبر"),
    }
    return mapping.get(key, ("muted", key))

def _order_label(info):
    state = info["order_state"]
    if state == "LOCKED_BUY_QUEUE": return "🔥 صف خرید قفل‌شده", "buy"
    if state == "LOCKED_SELL_QUEUE": return "🧊 صف فروش قفل‌شده", "sell"
    if state != "TWO_SIDED": return "⚪ داده تابلو ناکافی", "muted"
    pressure = info["order_pressure"]
    labels = {
        "BUY_HEAVY": "🟢 فشار خرید", "SELL_HEAVY": "🔴 فشار فروش", "BALANCED": "⚪ متعادل",
    }
    cls = "buy" if pressure == "BUY_HEAVY" else ("sell" if pressure == "SELL_HEAVY" else "muted")
    suffix = f" ({info['imbalance']:+.1f}٪)" if info["imbalance"] is not None else ""
    return labels.get(pressure, "⚪ نامشخص") + suffix, cls

def generate():
    cards = [_symbol_info(name, db) for name, db in SYMBOL_DBS]
    positions = _open_positions()
    wins, losses, pending, total, wr = _ai_stats()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def score_color(cls):
        return {"buy": "var(--good)", "sell": "var(--bad)", "watch": "var(--accent)"}.get(cls, "var(--muted)")

    card_html = ""
    for info in cards:
        sig_cls, sig_text = _sig_meta(info["signal"]["type"])
        order_text, order_cls = _order_label(info)
        score = float(info["signal"]["score"] or 0)
        score_pct = max(0, min(100, abs(score) if score <= 100 else 100))
        price = f"{info['price']:,.0f}" if info["price"] else "—"

        chips = f'<span class="chip {order_cls}">{_esc(order_text)}</span>'
        if info["gamma_wall"]:
            regime = {"CALL_HEAVY": "کال‌سنگین", "PUT_HEAVY": "پوت‌سنگین", "BALANCED": "متعادل"}.get(info["gamma_regime"], info["gamma_regime"] or "")
            chips += f'<span class="chip muted">🧲 دیواره {info["gamma_wall"]:,.0f} ({_esc(regime)})</span>'
        if info["news_count"]:
            chips += f'<span class="chip muted">📰 {info["news_count"]} خبر امروز</span>'

        contract_html = ""
        opt = info["signal"].get("option")
        if sig_cls in ("buy", "sell") and opt:
            details = info["signal"].get("details")
            sl = t1 = t2 = None
            try:
                parsed = json.loads(details) if details else {}
                sl = parsed.get("stop_loss") or (parsed.get("option") or {}).get("stop_loss")
                t1 = parsed.get("target1") or (parsed.get("option") or {}).get("target1")
                t2 = parsed.get("target2") or (parsed.get("option") or {}).get("target2")
            except Exception:
                pass
            rows = []
            if sl: rows.append(f'<span class="mini bad">SL {sl:,.0f}</span>')
            if t1: rows.append(f'<span class="mini good">TP۱ {t1:,.0f}</span>')
            if t2: rows.append(f'<span class="mini good">TP۲ {t2:,.0f}</span>')
            contract_html = f'''
            <div class="contract">
              <div class="contract-head">🎯 {_esc(opt)}</div>
              <div class="contract-targets">{"".join(rows)}</div>
            </div>'''

        card_html += f'''
        <article class="card {sig_cls}">
          <div class="card-top">
            <h2>{_esc(info["name"])}</h2>
            <div class="price">{price}<span class="unit"> ریال</span></div>
          </div>
          <div class="signal-row">
            <span class="badge {sig_cls}">{_esc(sig_text)}</span>
            <span class="score-num">{score:.0f}</span>
          </div>
          <div class="score-bar"><div class="score-fill" style="width:{score_pct}%;background:{score_color(sig_cls)}"></div></div>
          <div class="chips">{chips}</div>
          {contract_html}
        </article>'''

    pos_rows = ""
    if positions:
        for p in positions:
            pct = p.get("pct")
            pct_cls = "good" if (pct or 0) >= 0 else "bad"
            pct_txt = f"{pct:+.1f}٪" if pct is not None else "—"
            outcome_txt = {"PENDING": "باز", "T1_HIT": "نیم‌فروخته"}.get(p.get("outcome"), p.get("outcome") or "")
            pos_rows += f'''
            <div class="pos-row">
              <span class="pos-stock">{_esc(p["stock"])}</span>
              <span class="pos-sym">{_esc(p["symbol"])}</span>
              <span class="pos-entry">ورود {p["entry"]:,.0f}</span>
              <span class="pos-current">فعلی {p["current"]:,.0f}</span>
              <span class="pos-pct {pct_cls}">{pct_txt}</span>
              <span class="pos-status">{_esc(outcome_txt)}</span>
            </div>'''
    else:
        pos_rows = '<div class="empty">هیچ پوزیشن باز فعالی نیست.</div>'

    wr_txt = f"{wins} برد / {losses} باخت (نرخ برد {wr}٪)" if (wins or losses) else "هنوز معامله‌ای تسویه نشده"

    html_doc = f'''<!DOCTYPE html>
<html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{REFRESH_SECONDS}">
<title>AHRAM AI PRO</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#0E1013; --surface:#171A1F; --surface-2:#1D2128;
  --accent:#C99A3E; --good:#4CAE8C; --bad:#D66A5C; --muted:#7D8590;
  --text:#EDEBE6; --text-dim:#9BA1AC; --border:#2A2D33;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:'Vazirmatn',Tahoma,sans-serif;
  font-feature-settings:'tnum' 1;line-height:1.6;padding:28px 20px 60px}}
.wrap{{max-width:1180px;margin:0 auto}}
header{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;
  margin-bottom:26px;padding-bottom:16px;border-bottom:1px solid var(--border)}}
header h1{{font-size:22px;font-weight:700;margin:0;letter-spacing:.2px}}
header .meta{{color:var(--text-dim);font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:28px}}
.card{{background:var(--surface);border:1px solid var(--border);border-right:4px solid var(--muted);
  border-radius:10px;padding:18px 20px}}
.card.buy{{border-right-color:var(--good)}}
.card.sell{{border-right-color:var(--bad)}}
.card.watch{{border-right-color:var(--accent)}}
.card-top{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}}
.card-top h2{{font-size:17px;font-weight:600;margin:0;color:var(--text)}}
.price{{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}}
.price .unit{{font-size:12px;font-weight:400;color:var(--text-dim)}}
.signal-row{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.badge{{display:inline-block;padding:5px 14px;border-radius:999px;font-size:13px;font-weight:600}}
.badge.buy{{background:rgba(76,174,140,.15);color:var(--good)}}
.badge.sell{{background:rgba(214,106,92,.15);color:var(--bad)}}
.badge.watch{{background:rgba(201,154,62,.15);color:var(--accent)}}
.badge.muted{{background:rgba(125,133,144,.15);color:var(--muted)}}
.score-num{{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--text-dim)}}
.score-bar{{height:7px;border-radius:99px;background:var(--surface-2);overflow:hidden;margin-bottom:14px}}
.score-fill{{height:100%;border-radius:99px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chip{{font-size:12px;padding:4px 10px;border-radius:7px;background:var(--surface-2);color:var(--text-dim)}}
.chip.buy{{color:var(--good)}}
.chip.sell{{color:var(--bad)}}
.contract{{margin-top:14px;padding:12px 14px;background:var(--surface-2);border-radius:8px}}
.contract-head{{font-size:14px;font-weight:600;margin-bottom:6px}}
.contract-targets{{display:flex;gap:8px;flex-wrap:wrap}}
.mini{{font-size:12px;padding:3px 9px;border-radius:6px;font-weight:600;font-variant-numeric:tabular-nums}}
.mini.good{{background:rgba(76,174,140,.15);color:var(--good)}}
.mini.bad{{background:rgba(214,106,92,.15);color:var(--bad)}}
section.panel{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:18px 20px;margin-bottom:16px}}
section.panel h3{{font-size:15px;font-weight:600;margin:0 0 14px}}
.pos-row{{display:grid;grid-template-columns:70px 100px 1fr 1fr 80px 90px;gap:10px;align-items:center;
  padding:9px 0;border-bottom:1px solid var(--border);font-size:13px}}
.pos-row:last-child{{border-bottom:none}}
.pos-stock{{font-weight:600}}
.pos-sym{{color:var(--text-dim);font-variant-numeric:tabular-nums}}
.pos-entry,.pos-current{{color:var(--text-dim);font-variant-numeric:tabular-nums}}
.pos-pct{{font-weight:700;font-variant-numeric:tabular-nums}}
.pos-pct.good{{color:var(--good)}}
.pos-pct.bad{{color:var(--bad)}}
.pos-status{{color:var(--text-dim);font-size:12px}}
.empty{{color:var(--text-dim);font-size:13px}}
.footer-bar{{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:var(--text-dim);font-size:12px;
  padding-top:10px}}
@media(max-width:640px){{
  .pos-row{{grid-template-columns:1fr 1fr;row-gap:4px}}
}}
</style>
</head><body>
<div class="wrap">
<header>
  <h1>AHRAM AI PRO</h1>
  <span class="meta">به‌روزرسانی خودکار هر {REFRESH_SECONDS} ثانیه · آخرین بروزرسانی {now}</span>
</header>
<div class="cards">{card_html}</div>
<section class="panel">
  <h3>📌 پوزیشن‌های باز</h3>
  {pos_rows}
</section>
<div class="footer-bar">
  <span>📊 {wr_txt}</span>
  <span>برای جزئیات کامل (زنجیره آپشن، استراتژی‌ها، Greeks): options_dashboard_AHRAM_LIVE4.html</span>
</div>
</div>
</body></html>'''
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html_doc)
        with open(OUTPUT_FILE_VIP5, "w", encoding="utf-8") as f:
            f.write(html_doc)
        return OUTPUT_FILE
    except Exception as e:
        print("[DASHBOARD] ERROR:", e)
        return None

if __name__ == "__main__":
    out = generate()
    if out:
        print(f"✅ داشبورد ساخته شد: {out} + {OUTPUT_FILE_VIP5}")