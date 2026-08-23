# -*- coding: utf-8 -*-
"""
AHRAM DASHBOARD v4 - خواندن از هر ۳ دیتابیس (نسخه‌ی اصلاح‌شده)

اصلاحات نسبت به v3:
  - کارت هر نماد دیگه «پرحجم‌ترین CALL» رو از جدول options حدس نمی‌زنه (که
    می‌تونست با تصمیم واقعی ربات فرق داشته باشه و در صورت volume=0 موندن
    در آخرین snapshot، کارت خالی بمونه)؛ حالا مستقیم از signal_history
    آخرین آپشنی که واقعاً توسط ربات انتخاب/سیگنال شده رو نشون می‌ده
    (چه CALL چه PUT).
  - «پوزیشن‌های باز» یه باگ داشت: به ستون entry_price (که اصلاً وجود نداره)
    کوئری می‌زد، همیشه silently خالی می‌موند. اصلاح شد -> از option_price.
  - یه ارزیابی سبک نتیجه (WIN/LOSS/T1_HIT) اضافه شد که با قیمت فعلی آپشن
    مقایسه می‌کنه، چون قبلاً هیچ‌جا outcome آپدیت نمی‌شد و آمار هوش مصنوعی
    همیشه صفر می‌موند.
"""
import sqlite3
import os
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


def _update_pending_outcomes(cur, conn):
    """قیمت فعلی هر آپشن باز رو با هدف/حد ضررش مقایسه می‌کنه و outcome رو
    آپدیت می‌کنه. بدون این، ستون outcome همیشه روی PENDING می‌مونه و آمار
    هوش مصنوعی هیچ‌وقت معنادار نمی‌شه.

    نکته: چون سیگنال هر سیکل که BUY تکرار بشه دوباره لاگ می‌شه (برای
    تاریخچه‌ی فعالیت روزانه)، یه قرارداد واحد می‌تونه ده‌ها ردیف PENDING
    داشته باشه. این‌ها یه معامله‌ن، نه چندتا -- پس با هم (بر پایه‌ی قیمت
    ورودِ اولین ردیف) به‌عنوان یه گروه بسته می‌شن، وگرنه آمار و داده‌ی
    آموزشی ML مصنوعاً چند برابر می‌شه."""
    rows = _safe(
        cur,
        "SELECT option_symbol, option_price, stop_loss, target1, target2, outcome, MIN(id) "
        "FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') "
        "AND option_symbol IS NOT NULL AND option_symbol != '' GROUP BY option_symbol",
    )
    changed = False
    for sym, entry, sl, t1, t2, outcome, _min_id in rows:
        try:
            entry_f = float(entry) if entry else 0
            if entry_f <= 0:
                continue
            cur.execute(
                "SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1",
                (sym,),
            )
            pr = cur.fetchone()
            if not pr or not pr[0]:
                continue
            cur_price = float(pr[0])
            sl_f = float(sl) if sl else None
            t1_f = float(t1) if t1 else None
            t2_f = float(t2) if t2 else None

            new_outcome = None
            if sl_f and cur_price <= sl_f:
                new_outcome = "LOSS"
            elif t2_f and cur_price >= t2_f:
                new_outcome = "WIN"
            elif t1_f and cur_price >= t1_f and outcome == "PENDING":
                new_outcome = "T1_HIT"

            if new_outcome and new_outcome != outcome:
                pct = round(((cur_price - entry_f) / entry_f) * 100, 1)
                cur.execute(
                    "UPDATE signal_history SET outcome=?, outcome_pct=? "
                    "WHERE option_symbol=? AND outcome IN ('PENDING','T1_HIT')",
                    (new_outcome, pct, sym),
                )
                changed = True
        except Exception:
            continue
    if changed:
        conn.commit()


def _symbol_info(db):
    """قیمت سهم + آخرین آپشنی که واقعاً توسط ربات انتخاب/سیگنال شده + گاما
    اکسپوژر اکتشافی (فقط نمایشی، روی هیچ تصمیمی اثر نداره)."""
    info = {
        "price": "-",
        "opt_sym": "—", "opt_strike": "—", "opt_price": "—",
        "opt_type": None, "opt_days": "—", "opt_vol": 0,
        "opt_time": None,
        "gamma_wall": None, "gamma_regime": None, "gamma_conf": None,
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
        pass

    raw_symbol = None
    try:
        cur.execute(
            "SELECT option_symbol, strike_price, option_price, signal_type, time "
            "FROM signal_history WHERE option_symbol IS NOT NULL AND option_symbol != '' "
            "ORDER BY id DESC LIMIT 1"
        )
        r = cur.fetchone()
        if r:
            raw_symbol = r[0]
            info["opt_sym"] = r[0] or "—"
            info["opt_strike"] = f"{int(r[1]):,}" if r[1] else "—"
            info["opt_price"] = f"{int(r[2]):,}" if r[2] else "—"
            st = (r[3] or "").upper()
            info["opt_type"] = "PUT" if "PUT" in st else ("CALL" if "CALL" in st or "BUY" in st else None)
            info["opt_time"] = r[4]
    except Exception:
        pass

    if raw_symbol:
        try:
            cur.execute(
                "SELECT days_to_expire, volume FROM options WHERE symbol=? "
                "ORDER BY id DESC LIMIT 1",
                (raw_symbol,),
            )
            r = cur.fetchone()
            if r:
                info["opt_days"] = r[0] if r[0] is not None else "—"
                info["opt_vol"] = int(r[1]) if r[1] else 0
        except Exception:
            pass

    conn.close()

    try:
        from gamma_exposure import analyze_gamma_exposure
        gx = analyze_gamma_exposure(db)
        if gx.get("gamma_wall"):
            info["gamma_wall"] = gx["gamma_wall"]
            info["gamma_regime"] = gx["regime_bias"]
            info["gamma_conf"] = gx["confidence"]
    except Exception:
        pass

    return info


def _all_signals(limit=20):
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
        rows.extend(res)
        conn.close()
    rows.sort(key=lambda x: x[0] or "", reverse=True)
    return rows[:limit]


def _open_positions():
    """پوزیشن‌های باز از همه‌ی دیتابیس‌ها -- از option_price به‌عنوان قیمت
    ورود استفاده می‌کنه (ستون entry_price اصلاً وجود نداشت، همیشه خالی
    برمی‌گشت). یه ردیف در ازای هر option_symbol (نه هر بار که سیگنال تکرار
    شده)، وگرنه یه معامله‌ی واحد ده‌ها بار جداگانه لیست می‌شه."""
    out = []
    for _name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        _update_pending_outcomes(cur, conn)
        rows = _safe(
            cur,
            "SELECT symbol, option_symbol, option_price, stop_loss, target1, target2, outcome, MIN(id) "
            "FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') "
            "AND option_symbol IS NOT NULL AND option_symbol != '' GROUP BY option_symbol",
        )
        for stock_name, sym, entry, sl, t1, t2, outcome, _min_id in rows:
            cur.execute(
                "SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1",
                (sym,),
            )
            pr = cur.fetchone()
            entry_f = float(entry) if entry else 0
            cur_f = float(pr[0]) if pr and pr[0] else entry_f
            pct = round(((cur_f - entry_f) / entry_f) * 100, 1) if entry_f else 0
            out.append(
                (stock_name, sym, int(entry_f), int(float(t1) if t1 else 0),
                 int(float(t2) if t2 else 0), int(float(sl) if sl else 0),
                 int(cur_f), pct, outcome)
            )
        conn.close()
    return out


def _ai_stats():
    """برد/باخت/باز رو بر اساس option_symbol یکتا می‌شمره (نه هر ردیف تکراری
    که هر سیکل برای یه معامله‌ی واحد لاگ می‌شه)، وگرنه آمار مصنوعاً چند
    برابر نشون داده می‌شه. "کل سیگنال‌ها" (total) استثنا -- اون واقعاً
    باید هر ردیف فعالیت رو بشمره، چون هدفش گزارش فعالیت روزانه‌ست."""
    wins = losses = pending = total = 0
    for _name, db in SYMBOL_DBS:
        conn = _connect(db)
        if not conn:
            continue
        cur = conn.cursor()
        w = _safe(cur, "SELECT COUNT(DISTINCT option_symbol) FROM signal_history WHERE outcome='WIN'")
        l = _safe(cur, "SELECT COUNT(DISTINCT option_symbol) FROM signal_history WHERE outcome='LOSS'")
        p = _safe(cur, "SELECT COUNT(DISTINCT option_symbol) FROM signal_history WHERE outcome IN ('PENDING','T1_HIT') "
                       "AND option_symbol IS NOT NULL AND option_symbol != ''")
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
        if info["opt_sym"] == "—":
            opt_block = '<div class="optlabel">آخرین آپشن انتخابی</div><div class="optline muted">هنوز سیگنالی با آپشن ثبت نشده</div>'
        else:
            type_badge = ""
            if info["opt_type"] == "CALL":
                type_badge = '<span class="typebadge call">CALL</span>'
            elif info["opt_type"] == "PUT":
                type_badge = '<span class="typebadge put">PUT</span>'
            opt_block = f"""<div class="optlabel">آخرین آپشن انتخابی</div>
        <div class="optline"><b>{info['opt_sym']}</b> {type_badge} · اعمال {info['opt_strike']}</div>
        <div class="optline">قیمت {info['opt_price']} · {info['opt_days']} روز تا سررسید · حجم {vol_str}</div>"""

        gamma_block = ""
        if info.get("gamma_wall"):
            regime_fa = {"CALL_HEAVY": "کال‌سنگین", "PUT_HEAVY": "پوت‌سنگین", "BALANCED": "متعادل"}.get(
                info["gamma_regime"], info["gamma_regime"]
            )
            gamma_block = f"""
      <div class="optbox">
        <div class="optlabel">گاما اکسپوژر (اکتشافی)</div>
        <div class="optline">دیواره {info['gamma_wall']:,.0f} · رژیم {regime_fa} · اطمینان {info['gamma_conf']}</div>
      </div>"""

        card_html += f"""
    <div class="symcard">
      <div class="symname">{name}</div>
      <div class="symprice">{info['price']} <span class="unit">ریال</span></div>
      <div class="optbox">
        {opt_block}
      </div>{gamma_block}
    </div>"""

    pos_html = ""
    if positions:
        for stock_name, sym, entry, t1, t2, stop, current, pct, outcome in positions:
            color = "#1a9850" if pct >= 0 else "#d73027"
            badge_map = {"PENDING": ("باز", "#4ea8de"), "T1_HIT": ("نیم‌فروخته شده", "#f1a340")}
            badge_txt, badge_color = badge_map.get(outcome, ("باز", "#4ea8de"))
            pos_html += f"""
      <tr>
        <td><b>{stock_name}</b><div class="subtext">{sym}</div></td>
        <td>{entry:,}</td><td>{t1:,}</td><td>{t2:,}</td>
        <td>{stop:,}</td><td>{current:,}</td>
        <td style="color:{color};font-weight:bold">{pct:+}%</td>
        <td><span class="badge" style="background:{badge_color}">{badge_txt}</span></td>
      </tr>"""
    else:
        pos_html = '<tr><td colspan="8" class="empty">پوزیشن بازی نیست — هنوز سیگنال BUY صادر نشده</td></tr>'

    hist_html = ""
    if signals:
        for t, sym, st, sc, out, out_pct in signals:
            c = {"BUY": "#1a9850", "BUY_CALL": "#1a9850", "BUY_PUT": "#d73027",
                 "STRONG BUY": "#1a9850", "WATCH": "#f1a340", "WAIT": "#888"}.get(st, "#888")
            out_txt = '<span class="muted">—</span>'
            if out == "WIN":
                out_txt = f'<span style="color:#1a9850">برد {out_pct:+}%</span>'
            elif out == "LOSS":
                out_txt = f'<span style="color:#d73027">باخت {out_pct:+}%</span>'
            elif out == "T1_HIT":
                out_txt = '<span style="color:#f1a340">هدف اول</span>'
            elif out == "PENDING" and sym:
                out_txt = '<span style="color:#4ea8de">باز</span>'
            hist_html += (
                f"<tr><td class='timecell'>{t}</td><td>{sym or '-'}</td>"
                f"<td style='color:{c}'>{st}</td><td>{sc if sc is not None else '-'}</td>"
                f"<td>{out_txt}</td></tr>"
            )
    else:
        hist_html = '<tr><td colspan="5" class="empty">هنوز سیگنالی ثبت نشده</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="{REFRESH_SECONDS}">
<title>داشبورد نوسان‌گیری آپشن</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'Vazirmatn', Tahoma, 'Segoe UI', sans-serif;
    background: radial-gradient(circle at 10% 0%, #151923 0%, #0b0d12 55%);
    color: #e8e8e8; padding: 22px; margin: 0; min-height: 100vh;
  }}
  .topbar {{ display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }}
  h1 {{ color: #4caf50; font-size: 22px; margin: 0; letter-spacing: .3px; }}
  .updated {{ color: #7a8090; font-size: 12px; display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; background: #4caf50; box-shadow: 0 0 8px #4caf50; animation: pulse 2s infinite; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.35}} }}

  .signal-big {{
    font-size: 24px; font-weight: bold; padding: 18px; border-radius: 14px;
    text-align: center; margin-bottom: 20px; color: #fff;
    box-shadow: 0 8px 24px -8px rgba(0,0,0,.6);
  }}

  .symrow {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin-bottom: 24px; }}
  .symcard {{
    background: linear-gradient(180deg, #1c202b 0%, #171a22 100%);
    border: 1px solid #262b38; border-radius: 14px; padding: 18px;
    transition: border-color .2s; 
  }}
  .symcard:hover {{ border-color: #3a4256; }}
  .symname {{ color: #6fd88a; font-size: 15px; font-weight: bold; margin-bottom: 4px; }}
  .symprice {{ font-size: 27px; font-weight: bold; color: #fff; }}
  .unit {{ font-size: 12px; color: #7a8090; font-weight: normal; }}
  .optbox {{ margin-top: 14px; padding-top: 12px; border-top: 1px dashed #2a2e38; }}
  .optlabel {{ color: #7a8090; font-size: 11px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .4px; }}
  .optline {{ font-size: 12.5px; color: #c4c8d4; line-height: 1.8; }}
  .optline.muted {{ color: #565b6b; font-style: italic; }}
  .typebadge {{ font-size: 10px; padding: 1px 7px; border-radius: 6px; font-weight: bold; margin-right: 4px; }}
  .typebadge.call {{ background: rgba(26,152,80,.18); color: #4fd486; }}
  .typebadge.put {{ background: rgba(215,48,39,.18); color: #ff6b5e; }}

  section {{ margin-bottom: 24px; }}
  h2 {{ font-size: 14.5px; color: #b7bcc9; border-bottom: 1px solid #262b38; padding-bottom: 8px; margin-bottom: 12px; font-weight: 600; }}

  table {{ width: 100%; border-collapse: collapse; background: #171a22; border-radius: 12px; overflow: hidden; }}
  td, th {{ padding: 10px 12px; border-bottom: 1px solid #22262f; text-align: right; font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  th {{ background: #1e222c; color: #8a90a0; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .3px; }}
  tbody tr:hover {{ background: #1c2029; }}
  .subtext {{ color: #6a7080; font-size: 10.5px; margin-top: 2px; }}
  .timecell {{ color: #8a90a0; font-size: 12px; white-space: nowrap; }}
  .badge {{ padding: 3px 10px; border-radius: 10px; font-size: 11px; color: #fff; font-weight: 600; }}
  .empty {{ color: #565b6b; text-align: center; padding: 22px 0; }}
  .muted {{ color: #565b6b; }}

  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
  .stat {{ background: #171a22; border: 1px solid #262b38; border-radius: 12px; padding: 14px 16px; }}
  .stat .l {{ color: #7a8090; font-size: 11.5px; margin-bottom: 4px; }}
  .stat .v {{ font-size: 20px; font-weight: bold; color: #fff; }}
  .note {{ color: #565b6b; font-size: 11.5px; margin-top: 10px; }}
</style>
</head>
<body>
<div class="topbar">
  <h1>🚀 داشبورد نوسان‌گیری آپشن</h1>
  <div class="updated"><span class="dot"></span>{now_str} · هر {REFRESH_SECONDS} ثانیه به‌روز می‌شه</div>
</div>

<div class="signal-big" style="background:{sig_color};">
  آخرین سیگنال: {sig_fa}
</div>

<section>
  <h2>📊 نمادها + آخرین آپشن انتخابی ربات</h2>
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
  <div class="note">وضعیت (برد/باخت) با مقایسه‌ی خودکار قیمت فعلی آپشن با هدف/حد ضرر تعیین می‌شه؛ برای آموزش هوش مصنوعی به حداقل ۲۰ سیگنال ارزیابی‌شده نیاز است.</div>
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