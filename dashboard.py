# -*- coding: utf-8 -*-
"""
AHRAM DASHBOARD v3 - خواندن از هر ۳ دیتابیس
"""
import sqlite3
import os
from datetime import datetime

OUTPUT_FILE = "dashboard.html"

# هر نماد + دیتابیس اخصاصی
SYMBOL_DBS = [
    ("اهرم", "ahram_v2.db"),
    ("وبملت", "webmellt.db"),
    ("شستا", "shasta.db"),
]


def _connect(db):
    try:
        if not os.path.exists(db):
            return None
        return sqlite3.connect(db)
    except Exception:
        return None


def _safe(cur, sql, args=()):
    try:
        cur.execute(sql, args)
        return cur.fetchall()
    except Exception:
        return []


def _symbol_info(db):
    """قیمت سهم + بهترین آپشن CALL برای یک نماد."""
    info = {
        "price": "-", "ygap": None,
        "opt_sym": "—", "opt_strike": "—", "opt_price": "—",
        "opt_days": "—", "opt_vol": 0,
    }
    conn = _connect(db)
    if not conn:
        info["price"] = "دیتابیس نیست"
        return info
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT last_price FROM prices WHERE last_price IS NOT NULL "
            "AND last_price>0 ORDER BY id DESC LIMIT 1"
        )
        r = cur.fetchone()
        last = float(r[0]) if r and r[0] else None
        if last:
            info["price"] = f"{int(last):,}"
    except Exception:
        last = None

    try:
        cur.execute("SELECT MAX(time) FROM options")
        mt = cur.fetchone()[0]
        if mt:
            cur.execute(
                "SELECT symbol, strike_price, option_price, days_to_expire, volume "
                "FROM options WHERE option_type='CALL' AND time=? AND volume>0 "
                "ORDER BY volume DESC LIMIT 1",
                (mt,),
            )
            r = cur.fetchone()
            if r:
                info["opt_sym"] = r[0] or "—"
                info["opt_strike"] = f"{int(r[1]):,}" if r[1] else "—"
                info["opt_price"] = f"{int(r[2]):,}" if r[2] else "—"
                info["opt_days"] = r[3] if r[3] is not None else "—"
                info["opt_vol"] = int(r[4]) if r[4] else 0
    except Exception:
        pass

    conn.close()
    return info


def _all_signals(limit=20):
    """جمع‌آوری تاریخچه سیگنال از همه دیتابیس‌ها."""
    rows = []
    for _name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        res = _safe(
            cur,
            "SELECT time, symbol, signal_type, composite_score, outcome, outcome_pct "
            "FROM signal_history ORDER BY id DESC LIMIT 30",
        )
        for r in res:
            rows.append(r)
        conn.close()
    rows.sort(key=lambda x: x[0] or "", reverse=True)
    return rows[:limit]


def _open_positions():
    """پوزیشن‌های باز از همه دیتابیس‌ها."""
    out = []
    for _name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        rows = _safe(
            cur,
            "SELECT symbol, entry_price, stop_loss, target1, target2, outcome "
            "FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') ORDER BY id DESC",
        )
        for sym, entry, sl, t1, t2, outcome in rows:
            cur.execute(
                "SELECT option_price FROM options WHERE symbol=? "
                "ORDER BY id DESC LIMIT 1",
                (sym,),
            )
            pr = cur.fetchone()
            entry_f = float(entry) if entry else 0
            cur_f = float(pr[0]) if pr and pr[0] else entry_f
            pct = round(((cur_f - entry_f) / entry_f) * 100, 1) if entry_f else 0
            out.append(
                (sym, int(entry_f), int(float(t1) if t1 else 0),
                 int(float(t2) if t2 else 0), int(float(sl) if sl else 0),
                 int(cur_f), pct, outcome)
            )
        conn.close()
    return out


def _ai_stats():
    wins = losses = pending = total = 0
    for _name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        w = _safe(cur, "SELECT COUNT(*) FROM signal_history WHERE outcome='WIN'")
        l = _safe(cur, "SELECT COUNT(*) FROM signal_history WHERE outcome='LOSS'")
        p = _safe(cur, "SELECT COUNT(*) FROM signal_history WHERE outcome IN ('PENDING','T1_HIT')")
        t = _safe(cur, "SELECT COUNT(*) FROM signal_history")
        wins += w[0][0] if w else 0
        losses += l[0][0] if l else 0
        pending += p[0][0] if p else 0
        total += t[0][0] if t else 0
        conn.close()
    wr = round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0
    return wins, losses, pending, total, wr


def generate():
    cards = []
    latest_sig = None
    for name, db in SYMBOL_DBS:
        info = _symbol_info(db)
        cards.append((name, info))

    signals = _all_signals(20)
    if signals:
        latest_sig = signals[0]

    positions = _open_positions()
    wins, losses, pending, total, wr = _ai_stats()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sig_type = latest_sig[2] if latest_sig else "WAIT"
    sig_map = {
        "BUY": ("#1a9850", "🟢 خرید"),
        "BUY_CALL": ("#1a9850", "🟢 خرید کال"),
        "BUY_PUT": ("#d73027", "🔴 خرید پوت"),
        "STRONG BUY": ("#1a9850", "🟢 خرید قوی"),
        "WATCH": ("#f1a340", "🟡 تحت نظر"),
        "WAIT": ("#5a6070", "⚪ صبر"),
    }
    sig_color, sig_fa = sig_map.get(sig_type, ("#5a6070", "⚪ صبر"))

    card_html = ""
    for name, info in cards:
        vol_str = f"{info['opt_vol']:,}" if info["opt_vol"] else "—"
        card_html += f"""
    <div class="symcard">
      <div class="symname">{name}</div>
      <div class="symprice">{info['price']} <span class="unit">ریال</span></div>
      <div class="optbox">
        <div class="optlabel">پرطرفدارترین CALL</div>
        <div class="optline"><b>{info['opt_sym']}</b> · strike {info['opt_strike']}</div>
        <div class="optline">قیمت {info['opt_price']} · {info['opt_days']} روز · حجم {vol_str}</div>
      </div>
    </div>"""

    pos_html = ""
    if positions:
        for sym, entry, t1, t2, stop, current, pct, outcome in positions:
            color = "#1a9850" if pct >= 0 else "#d73027"
            badge = "نیم‌فروخته شده" if outcome == "T1_HIT" else "باز"
            pos_html += f"""
      <tr>
        <td><b>{sym}</b></td><td>{entry:,}</td><td>{t1:,}</td><td>{t2:,}</td>
        <td>{stop:,}</td><td>{current:,}</td>
        <td style="color:{color};font-weight:bold">{pct:+}%</td>
        <td><span class="badge">{badge}</span></td>
      </tr>"""
    else:
        pos_html = '<tr><td colspan="8" class="empty">پوزیشن بازی نیست — هنوز سیگنال BUY صادر نشده</td></tr>'

    hist_html = ""
    if signals:
        for t, sym, st, sc, out, out_pct in signals:
            c = {"BUY": "#1a9850", "BUY_CALL": "#1a9850", "BUY_PUT": "#d73027", 
                 "STRONG BUY": "#1a9850", "WATCH": "#f1a340", "WAIT": "#888"}.get(st, "#888")
            out_txt = ""
            if out == "WIN":
                out_txt = f'<span style="color:#1a9850">برد {out_pct}%</span>'
            elif out == "LOSS":
                out_txt = f'<span style="color:#d73027">باخت {out_pct}%</span>'
            elif out in ("PENDING", "T1_HIT"):
                out_txt = '<span style="color:#4ea8de">باز</span>'
            hist_html += f"<tr><td>{t}</td><td>{sym or '-'}</td><td style='color:{c}'>{st}</td><td>{sc or '-'}</td><td>{out_txt}</td></tr>"
    else:
        hist_html = '<tr><td colspan="5" class="empty">هنوز سیگنالی ثبت نشده</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="20">
<title>داشبورد نوسان‌گیری آپشن</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: Tahoma, 'Segoe UI', sans-serif; background: #0f1115; color: #e8e8e8; padding: 18px; margin: 0; }}
  h1 {{ color: #4caf50; font-size: 21px; margin: 0 0 4px; }}
  .updated {{ color: #777; font-size: 12px; margin-bottom: 16px; }}
  .signal-big {{ font-size: 26px; font-weight: bold; padding: 16px; border-radius: 12px; text-align: center; margin-bottom: 18px; color: #fff; }}
  .symrow {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
  .symcard {{ flex: 1; min-width: 220px; background: #1b1e26; border: 1px solid #2a2e38; border-radius: 12px; padding: 16px; }}
  .symname {{ color: #4caf50; font-size: 16px; font-weight: bold; margin-bottom: 6px; }}
  .symprice {{ font-size: 26px; font-weight: bold; color: #fff; }}
  .unit {{ font-size: 12px; color: #888; font-weight: normal; }}
  .optbox {{ margin-top: 12px; padding-top: 10px; border-top: 1px solid #2a2e38; }}
  .optlabel {{ color: #777; font-size: 11px; margin-bottom: 5px; }}
  .optline {{ font-size: 12px; color: #bbb; line-height: 1.7; }}
  table {{ width: 100%; border-collapse: collapse; background: #1b1e26; border-radius: 10px; overflow: hidden; margin-bottom: 18px; }}
  td, th {{ padding: 9px 11px; border-bottom: 1px solid #2a2e38; text-align: right; font-size: 13px; }}
  th {{ background: #242834; color: #aaa; }}
  .badge {{ padding: 3px 9px; border-radius: 10px; font-size: 11px; color: #fff; background: #4ea8de; }}
  .empty {{ color: #777; text-align: center; }}
  section {{ margin-bottom: 22px; }}
  h2 {{ font-size: 15px; color: #ccc; border-bottom: 1px solid #2a2e38; padding-bottom: 6px; }}
  .stats {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .stat {{ background: #1b1e26; border: 1px solid #2a2e38; border-radius: 10px; padding: 12px 16px; min-width: 130px; }}
  .stat .l {{ color: #888; font-size: 12px; }}
  .stat .v {{ font-size: 19px; font-weight: bold; }}
  .note {{ color: #777; font-size: 12px; margin-top: 8px; }}
</style>
</head>
<body>
<h1>🚀 داشبورد نوسان‌گیری آپشن</h1>
<div class="updated">آخرین به‌روزرسانی: {now_str} (هر ۲۰ ثانیه خودکار) · نمادها: اهرم، وبملت، شستا</div>

<div class="signal-big" style="background:{sig_color};">
  آخرین سیگنال: {sig_fa}
</div>

<section>
  <h2>📊 نمادها + پرطرفدارترین آپشن CALL</h2>
  <div class="symrow">{card_html}</div>
</section>

<section>
  <h2>📋 پوزیشن‌های باز</h2>
  <table>
    <tr><th>نماد</th><th>ورودی</th><th>هدف ۱</th><th>هدف ۲</th><th>حد ضرر</th><th>قیمت فعلی</th><th>سود/زیان</th><th>وضعیت</th></tr>
    {pos_html}
  </table>
</section>

<section>
  <h2>📜 تاریخچه سیگنال‌ها</h2>
  <table>
    <tr><th>زمان</th><th>نماد</th><th>سیگنال</th><th>امتیاز</th><th>نتیجه</th></tr>
    {hist_html}
  </table>
</section>

<section>
  <h2>🧠 وضعیت هوش مصنوعی</h2>
  <div class="stats">
    <div class="stat"><div class="l">کل سیگنال‌ها</div><div class="v">{total}</div></div>
    <div class="stat"><div class="l">برد / باخت</div><div class="v">{wins} / {losses}</div></div>
    <div class="stat"><div class="l">نرخ برد</div><div class="v">{wr}%</div></div>
    <div class="stat"><div class="l">پوزیشن باز</div><div class="v">{pending}</div></div>
  </div>
  <div class="note">برای آموزش هوش مصنوعی به حداقل ۲۰ سیگنال ارزیابی‌شده نیاز است.</div>
</section>

</body>
</html>"""

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print("[DASHBOARD] ERROR:", e)
        return None
    return OUTPUT_FILE


if __name__ == "__main__":
    out = generate()
    if out:
        print(f"داشبورد ساخته شد: {out}")
        print("فایل dashboard.html رو با مرورگر باز کنید.")
