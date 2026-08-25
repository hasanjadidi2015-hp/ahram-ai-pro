# -*- coding: utf-8 -*-
"""AHRAM AI PRO — داشبورد نمایشی.

این فایل فقط داده‌های موجود را می‌خواند و نمایش می‌دهد؛ هیچ منطق سیگنال،
محاسبه، جدول اصلی یا قواعد معاملاتی را تغییر نمی‌دهد. تنها رفتار قبلیِ حفظ‌شده،
به‌روزرسانی نتیجه پوزیشن باز در صورت برخورد قیمت آپشن با حد/هدف است.
"""
import html
import os
import sqlite3
from datetime import datetime

OUTPUT_FILE = "dashboard.html"
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
    """رفتار قبلی داشبورد: بستن نتیجه پوزیشن‌های باز با هدف/حد ضرر."""
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
    rows = _safe(
        cur,
        "SELECT time, signal_type, composite_score, option_symbol, option_price, strike_price, "
        "stop_loss, target1, target2, details FROM signal_history ORDER BY id DESC LIMIT 1",
    )
    if not rows:
        return {"type": "WAIT", "score": None, "time": None, "option": None}
    t, st, score, sym, op, strike, sl, t1, t2, details = rows[0]
    return {
        "time": t, "type": (st or "WAIT").upper(), "score": score,
        "option": sym, "option_price": op, "strike": strike,
        "stop": sl, "t1": t1, "t2": t2, "details": details,
    }


def _symbol_info(name, db):
    info = {
        "name": name, "price": None, "price_time": None,
        "signal": {"type": "WAIT", "score": None, "time": None, "option": None},
        "option_days": None, "option_volume": None,
        "gamma_wall": None, "gamma_regime": None, "gamma_conf": None,
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
        rows = _safe(cur, "SELECT buy_price, sell_price, buy_volume, sell_volume FROM order_book ORDER BY id DESC LIMIT 5")
        if rows:
            buy_prices = [float(r[0] or 0) for r in rows]
            sell_prices = [float(r[1] or 0) for r in rows]
            buy_vol = sum(float(r[2] or 0) for r in rows)
            sell_vol = sum(float(r[3] or 0) for r in rows)
            has_buy, has_sell = any(buy_prices), any(sell_prices)
            if has_buy and not has_sell:
                info["order_state"] = "LOCKED_BUY_QUEUE"
                info["order_pressure"] = "BUY_QUEUE"
            elif has_sell and not has_buy:
                info["order_state"] = "LOCKED_SELL_QUEUE"
                info["order_pressure"] = "SELL_QUEUE"
            elif has_buy and has_sell and buy_vol + sell_vol > 0:
                info["order_state"] = "TWO_SIDED"
                info["imbalance"] = round((buy_vol - sell_vol) / (buy_vol + sell_vol) * 100, 1)
                best_buy = next((x for x in buy_prices if x > 0), 0)
                best_sell = next((x for x in sell_prices if x > 0), 0)
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


def _open_positions():
    output = []
    for name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        _update_pending_outcomes(cur, conn)
        rows = _safe(
            cur,
            "SELECT position_id, symbol, option_symbol, option_price, stop_loss, target1, target2, outcome, MIN(id) "
            "FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') AND position_id IS NOT NULL "
            "GROUP BY position_id",
        )
        for pos_id, stock, sym, entry, sl, t1, t2, outcome, _ in rows:
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
                "pct": gain, "outcome": outcome,
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
        all_rows.extend(_safe(
            cur,
            "SELECT time, symbol, signal_type, composite_score, option_symbol, outcome, outcome_pct "
            "FROM signal_history ORDER BY id DESC LIMIT 20",
        ))
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
    signals = _all_signals()
    news = _recent_news()
    wins, losses, pending, total, wr = _ai_stats()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    active = [c for c in cards if _sig_meta(c["signal"]["type"])[0] in ("buy", "sell")]
    best = max(active, key=lambda c: float(c["signal"]["score"] or 0), default=None)
    top_cls, top_text = _sig_meta(best["signal"]["type"] if best else "WATCH")

    card_html = ""
    for info in cards:
        sig_cls, sig_text = _sig_meta(info["signal"]["type"])
        order_text, order_cls = _order_label(info)
        option = _esc(info["signal"].get("option"))
        gamma = "—"
        if info["gamma_wall"]:
            regime = {"CALL_HEAVY": "کال‌سنگین", "PUT_HEAVY": "پوت‌سنگین", "BALANCED": "متعادل"}.get(info["gamma_regime"], info["gamma_regime"])
            gamma = f"دیواره {_fmt(info['gamma_wall'])} · {regime}"
        score = info["signal"].get("score")
        score_text = f"{int(float(score))}/100" if score is not None else "—"
        option_info = "بدون قرارداد منتخب"
        if info["signal"].get("option"):
            option_info = f"{option} · اعمال {_fmt(info['signal'].get('strike'))} · {info['option_days'] if info['option_days'] is not None else '—'} روز"
        card_html += f'''<article class="symbol-card {sig_cls}">
          <div class="card-head"><h3>{_esc(info['name'])}</h3><span class="pill {sig_cls}">{sig_text}</span></div>
          <div class="price">{_fmt(info['price'])}<small>ریال</small></div>
          <div class="score"><span>امتیاز تصمیم</span><b>{score_text}</b></div>
          <div class="meter"><i class="{sig_cls}" style="width:{min(100, max(0, float(score or 0)))}%"></i></div>
          <div class="contract">{option_info}</div>
          <div class="chips"><span class="chip {order_cls}">{order_text}</span><span class="chip muted">γ {gamma}</span></div>
        </article>'''

    position_html = ""
    for p in positions:
        cls = "buy" if p["pct"] >= 0 else "sell"
        state = "هدف اول" if p["outcome"] == "T1_HIT" else "باز"
        # نوار پیشرفت صرفاً تصویری: نقطه ورود=0، حدضرر=-12، هدف اول=+15
        progress = min(100, max(0, (p["pct"] + 12) / 27 * 100))
        position_html += f'''<div class="position-card">
          <div class="position-main"><div><span class="eyebrow">{_esc(p['stock'])} · {_esc(p['symbol'])}</span><strong class="{cls}">{_pct(p['pct'])}</strong></div><span class="pill info">{state}</span></div>
          <div class="track"><i style="width:{progress:.1f}%"></i><span class="entry">ورود</span><span class="t1">هدف ۱</span></div>
          <div class="position-data"><span>ورود <b>{_fmt(p['entry'])}</b></span><span>فعلی <b>{_fmt(p['current'])}</b></span><span>حدضرر <b>{_fmt(p['stop'])}</b></span><span>هدف ۱ <b>{_fmt(p['t1'])}</b></span><span>هدف ۲ <b>{_fmt(p['t2'])}</b></span></div>
        </div>'''
    if not position_html:
        position_html = '<div class="empty-state">پوزیشن بازی وجود ندارد.</div>'

    alert_items = []
    for info in cards:
        order_text, order_cls = _order_label(info)
        if order_cls in ("buy", "sell"):
            alert_items.append((order_cls, info["name"], order_text))
        latest = info.get("latest_news")
        if latest and latest.get("category") in ("توقف نماد", "عدم تأیید معاملات", "افشای اطلاعات بااهمیت"):
            alert_items.append(("watch", info["name"], f"خبر: {_esc(latest.get('category'))}"))
    alerts_html = "".join(f'<div class="alert {c}"><b>{_esc(n)}</b><span>{t}</span></div>' for c, n, t in alert_items[:6])
    if not alerts_html:
        alerts_html = '<div class="empty-state">هشدار فعال مهمی ثبت نشده است.</div>'

    news_html = ""
    for t, name, source, title, cat, event_date in news:
        news_html += f'''<div class="news-row"><span class="news-time">{_esc(event_date or t)}</span><span class="news-name">{_esc(name)}</span><span class="news-cat">{_esc(cat or source)}</span><span>{_esc(title)}</span></div>'''
    if not news_html:
        news_html = '<div class="empty-state">خبر رسمی ثبت‌شده‌ای وجود ندارد.</div>'

    hist_html = ""
    for t, name, st, score, option, outcome, out_pct in signals:
        cls, label = _sig_meta(st)
        result = "—"
        if outcome == "WIN": result = f'<span class="buy">برد {_pct(out_pct)}</span>'
        elif outcome == "LOSS": result = f'<span class="sell">باخت {_pct(out_pct)}</span>'
        elif outcome == "T1_HIT": result = '<span class="watch">هدف اول</span>'
        elif outcome == "PENDING" and option: result = '<span class="info-text">باز</span>'
        hist_html += f"<tr><td>{_esc((t or '')[11:16])}</td><td>{_esc(name)}</td><td><span class='pill {cls}'>{label}</span></td><td>{score if score is not None else '—'}</td><td>{_esc(option)}</td><td>{result}</td></tr>"
    if not hist_html:
        hist_html = '<tr><td colspan="6" class="empty-state">سیگنالی ثبت نشده است.</td></tr>'

    best_detail = "فعلاً شرایط ورود تازه تأیید نشده است."
    if best:
        s = best["signal"]
        best_detail = f"{_esc(best['name'])} · قرارداد {_esc(s.get('option'))} · ورود {_fmt(s.get('option_price'))} · حدضرر {_fmt(s.get('stop'))} · هدف اول {_fmt(s.get('t1'))}"

    html_doc = f'''<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="{REFRESH_SECONDS}"><title>AHRAM AI PRO</title>
<style>
:root{{--bg:#0b1220;--panel:#111c2e;--panel2:#17263d;--line:#263750;--text:#edf3ff;--muted:#94a3b8;--green:#22c55e;--red:#ef4444;--orange:#f59e0b;--blue:#38bdf8}}*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(145deg,#09111e,#0b1220 48%,#101827);color:var(--text);font-family:Vazirmatn,Tahoma,Arial,sans-serif;font-size:14px}}.shell{{max-width:1440px;margin:auto;padding:22px}}.top{{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:18px}}h1{{font-size:22px;margin:0}}.sub,.muted{{color:var(--muted)}}.status{{display:flex;gap:8px;flex-wrap:wrap}}.status span,.chip,.pill{{border-radius:999px;padding:5px 9px;font-size:11px;font-weight:700;white-space:nowrap}}.status span{{background:#152238;color:#cbd5e1}}.live{{color:#86efac!important}}.live:before{{content:'●';margin-left:5px}}.hero{{margin:18px 0;display:grid;grid-template-columns:1.1fr 2fr;gap:14px}}.hero-main,.hero-detail,.symbol-card,.panel,.position-card{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px}}.hero-main{{padding:18px;border-right:5px solid var(--green)}}.hero-main.sell{{border-color:var(--red)}}.hero-main.watch,.hero-main.muted{{border-color:var(--orange)}}.hero-label,.eyebrow{{color:var(--muted);font-size:12px}}.hero-action{{font-size:28px;font-weight:900;margin-top:7px}}.hero-detail{{padding:18px;display:flex;align-items:center;color:#d8e3f4}}.symbol-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.symbol-card{{padding:16px;min-width:0}}.symbol-card.buy{{border-top:3px solid var(--green)}}.symbol-card.sell{{border-top:3px solid var(--red)}}.symbol-card.watch,.symbol-card.muted{{border-top:3px solid var(--orange)}}.card-head,.position-main{{display:flex;justify-content:space-between;align-items:center;gap:8px}}h3{{margin:0;font-size:17px}}.price{{font-size:29px;font-weight:900;margin:15px 0 10px}}.price small{{font-size:11px;color:var(--muted);margin-right:5px}}.score{{display:flex;justify-content:space-between;color:var(--muted)}}.score b{{color:var(--text)}}.meter,.track{{height:7px;background:#223049;border-radius:9px;overflow:hidden;margin:8px 0 13px}}.meter i,.track i{{display:block;height:100%;background:var(--blue);border-radius:9px}}.meter i.buy{{background:var(--green)}}.meter i.sell{{background:var(--red)}}.meter i.watch,.meter i.muted{{background:var(--orange)}}.contract{{font-size:12px;border-top:1px solid var(--line);padding-top:11px;color:#d5dfef;min-height:38px}}.chips{{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}}.pill.buy,.chip.buy{{background:#123c29;color:#86efac}}.pill.sell,.chip.sell{{background:#4a1c25;color:#fca5a5}}.pill.watch,.chip.watch{{background:#4a3512;color:#fcd34d}}.pill.muted,.chip.muted{{background:#243147;color:#b6c4d8}}.pill.info{{background:#163a56;color:#7dd3fc}}.grid2{{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;margin-top:18px}}.panel{{padding:16px}}.panel h2{{font-size:15px;margin:0 0 13px}}.position-card{{padding:14px;margin-bottom:10px;background:#0d1829}}.position-card strong{{font-size:21px;display:block;margin-top:4px}}.buy{{color:#86efac}}.sell{{color:#fca5a5}}.watch{{color:#fcd34d}}.track{{position:relative;margin:13px 0 17px}}.track i{{background:linear-gradient(90deg,var(--red),var(--blue),var(--green))}}.track span{{position:absolute;top:11px;color:var(--muted);font-size:10px}}.track .entry{{right:42%}}.track .t1{{left:0}}.position-data{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;font-size:11px;color:var(--muted)}}.position-data b{{display:block;color:var(--text);font-size:13px;margin-top:3px}}.alert{{display:flex;gap:9px;padding:10px;border-bottom:1px solid var(--line)}}.alert:last-child{{border:0}}.alert b{{min-width:45px}}.alert.buy{{border-right:3px solid var(--green)}}.alert.sell{{border-right:3px solid var(--red)}}.alert.watch{{border-right:3px solid var(--orange)}}.news-row{{display:grid;grid-template-columns:92px 55px 105px 1fr;gap:8px;padding:10px 0;border-bottom:1px solid var(--line);font-size:12px}}.news-time,.news-cat{{color:var(--muted)}}.news-name{{font-weight:bold}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}}.stat{{background:var(--panel);border:1px solid var(--line);padding:14px;border-radius:13px}}.stat span{{color:var(--muted);font-size:12px}}.stat b{{font-size:23px;display:block;margin-top:5px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:right;font-size:12px}}th{{color:var(--muted);font-weight:600}}.history{{margin-top:18px}}.empty-state{{color:var(--muted);padding:18px;text-align:center}}.info-text{{color:#7dd3fc}}@media(max-width:850px){{.hero,.grid2{{grid-template-columns:1fr}}.symbol-grid{{grid-template-columns:1fr}}.top{{align-items:flex-start;flex-direction:column}}.position-data{{grid-template-columns:repeat(3,1fr)}}.news-row{{grid-template-columns:75px 45px 1fr}}.news-row span:last-child{{grid-column:1/-1}}.hide-mobile{{display:none}}.stats{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main class="shell">
<header class="top"><div><h1>🚀 AHRAM AI PRO</h1><div class="sub">داشبورد تصمیم‌یار آپشن · فقط نمایش داده‌های فعلی ربات</div></div><div class="status"><span class="live">سیستم فعال</span><span>به‌روزرسانی {REFRESH_SECONDS} ثانیه</span><span>{now}</span></div></header>
<section class="hero"><div class="hero-main {top_cls}"><div class="hero-label">بهترین اقدام فعلی</div><div class="hero-action">{top_text}</div></div><div class="hero-detail">{best_detail}</div></section>
<section class="symbol-grid">{card_html}</section>
<section class="grid2"><div class="panel"><h2>📌 پوزیشن‌های باز</h2>{position_html}</div><div class="panel"><h2>⚠️ هشدارها و وضعیت تابلو</h2>{alerts_html}</div></section>
<section class="grid2"><div class="panel"><h2>📰 آخرین رویدادهای رسمی</h2>{news_html}</div><div class="panel"><h2>🧠 وضعیت یادگیری</h2><div class="stats"><div class="stat"><span>کل رکوردها</span><b>{total}</b></div><div class="stat"><span>برد / باخت</span><b>{wins} / {losses}</b></div><div class="stat"><span>نرخ برد</span><b>{wr}٪</b></div><div class="stat"><span>پوزیشن باز</span><b>{pending}</b></div></div><div class="sub" style="margin-top:12px;font-size:11px">تا ثبت حداقل دادهٔ واقعی، ML صرفاً در حال جمع‌آوری داده است.</div></div></section>
<section class="panel history"><h2>📜 آخرین تصمیم‌ها <span class="sub">(۱۲ رکورد آخر)</span></h2><table><thead><tr><th>زمان</th><th>نماد</th><th>تصمیم</th><th>امتیاز</th><th class="hide-mobile">قرارداد</th><th>نتیجه</th></tr></thead><tbody>{hist_html}</tbody></table></section>
</main></body></html>'''
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html_doc)
        return OUTPUT_FILE
    except Exception as e:
        print("[DASHBOARD] ERROR:", e)
        return None


if __name__ == "__main__":
    out = generate()
    if out:
        print(f"✅ داشبورد ساخته شد: {out}")
