# -*- coding: utf-8 -*-
"""
AHRAM DASHBOARD  (داشبورد وب زنده)

یه صفحه‌ی HTML می‌سازه که خودش هر ۲۰ ثانیه آپدیت می‌شه.
نشان می‌دهد: قیمت اهرم، آخرین سیگنال، پوزیشن‌های باز (با اهداف)،
تاریخچه‌ی سیگنال‌ها و وضعیت هوش مصنوعی.

✅ نسخه‌ی مقاوم: خودش ستون‌های واقعیِ جداول (prices/options) رو با PRAGMA
   می‌شناسه، پس با تغییر schema (مثل V2) کرش نمی‌کنه و fallback بی‌خطر می‌کنه.
"""
import sqlite3
from datetime import datetime

import config

OUTPUT_FILE = "dashboard.html"


def _safe_query(cur, sql, args=()):
    try:
        cur.execute(sql, args)
        return cur.fetchall()
    except Exception:
        return []


def generate():
    """ساخت/به‌روزرسانی dashboard.html از دیتابیس."""
    try:
        conn = sqlite3.connect("ahram_v2.db")
    except Exception:
        return
    cur = conn.cursor()

    # ------------------------------------------------------------
    #  کشِ ستون‌های واقعیِ جداول (مقاوم در برابر تغییرِ schema مثل V2)
    # ------------------------------------------------------------
    def _cols(table):
        try:
            return {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        except Exception:
            return set()

    price_cols = _cols("prices")
    opt_cols = _cols("options")

    # ستونِ مناسبِ قیمت سهم (قدیمی: last_price | V2 OHLCV: close)
    prices_price = next((c for c in ("last_price", "close", "closing_price") if c in price_cols), None)
    # ستونِ مناسبِ قیمت آپشن (قدیمی: option_price | شاید V2: price/close)
    opt_price = next((c for c in ("option_price", "price", "last_price", "close") if c in opt_cols), None)

    # قیمت اهرم
    ahrm_price = "-"
    if prices_price:
        try:
            cur.execute(f"SELECT {prices_price} FROM prices ORDER BY id DESC LIMIT 1")
            r = cur.fetchone()
            if r and r[0]:
                ahrm_price = f"{int(r[0]):,}"
        except Exception:
            pass

    # بهترین اپشن اخیر (CALL پرحجم) — فقط با ستون‌های موجود
    best_opt = None
    try:
        if ("symbol" in opt_cols and "strike_price" in opt_cols
                and opt_price and "days_to_expire" in opt_cols):
            cur.execute(
                f"""SELECT symbol, strike_price, {opt_price}, days_to_expire
                    FROM options WHERE option_type='CALL'
                    ORDER BY id DESC LIMIT 1"""
            )
            best_opt = cur.fetchone()
    except Exception:
        best_opt = None

    # آخرین سیگنال
    last_signal = None
    try:
        cur.execute("""SELECT time, symbol, signal_type, composite_score, outcome
                       FROM signal_history ORDER BY id DESC LIMIT 1""")
        last_signal = cur.fetchone()
    except Exception:
        pass

    # پوزیشن‌های باز (PENDING / T1_HIT)
    open_positions = _safe_query(cur, """SELECT symbol, entry_price, stop_loss, target1, target2, outcome
                                          FROM signal_history
                                          WHERE outcome IN ('PENDING','T1_HIT')
                                          ORDER BY id DESC""")

    # قیمت فعلی هر پوزیشن باز (✅ مقاوم: ستونِ درست یا fallback به قیمت ورودی)
    open_rows = []
    for sym, entry, stop, t1, t2, outcome in open_positions:
        entry_f = float(entry) if entry else 0.0
        current = entry_f
        if opt_price:
            try:
                cur.execute(
                    f"SELECT {opt_price} FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1",
                    (sym,)
                )
                pr = cur.fetchone()
                if pr and pr[0]:
                    current = float(pr[0])
            except Exception:
                pass
        if not current:
            current = entry_f if entry_f else 1.0
        pct = round(((current - entry_f) / entry_f) * 100, 1) if entry_f else 0
        to_t1 = round(((float(t1) - current) / current) * 100, 1) if t1 and current else 0
        open_rows.append((sym, int(entry_f), int(float(t1) if t1 else 0), int(float(t2) if t2 else 0),
                          int(float(stop) if stop else 0), int(current), pct, to_t1, outcome))

    # تاریخچه‌ی اخیر
    history = _safe_query(cur, """SELECT time, symbol, signal_type, composite_score, outcome, outcome_pct
                                  FROM signal_history ORDER BY id DESC LIMIT 10""")

    # آمار هوش مصنوعی
    try:
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome='WIN'")
        wins = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome='LOSS'")
        losses = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome IN ('PENDING','T1_HIT')")
        pending = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signal_history")
        total_sig = cur.fetchone()[0]
    except Exception:
        wins = losses = pending = total_sig = 0

    conn.close()

    win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # رنگ آخرین سیگنال
    sig_type = last_signal[2] if last_signal else "WAIT"
    sig_color = {"BUY": "#1a9850", "WATCH": "#f1a340", "WAIT": "#888888"}.get(sig_type, "#888")
    sig_fa = {"BUY": "🟢 خرید", "WATCH": "🟡 تحت نظر", "WAIT": "⚪ صبر"}.get(sig_type, "⚪ صبر")

    # ردیف‌های پوزیشن باز
    pos_html = ""
    for sym, entry, t1, t2, stop, current, pct, to_t1, outcome in open_rows:
        color = "#1a9850" if pct >= 0 else "#d73027"
        badge = "نصف فروخته شد" if outcome == "T1_HIT" else "باز"
        pos_html += f"""
        <tr>
          <td><b>{sym}</b></td>
          <td>{entry:,}</td>
          <td>{t1:,}</td>
          <td>{t2:,}</td>
          <td>{stop:,}</td>
          <td>{current:,}</td>
          <td style="color:{color};font-weight:bold">{pct:+}%</td>
          <td><span class="badge" style="background:#2196F3">{badge}</span></td>
        </tr>"""

    # ردیف‌های تاریخچه
    hist_html = ""
    for t, sym, st, sc, out, out_pct in history:
        c = {"BUY": "#1a9850", "WATCH": "#f1a340", "WAIT": "#888"}.get(st, "#888")
        out_txt = ""
        if out == "WIN":
            out_txt = f'<span style="color:#1a9850">برد {out_pct}%</span>'
        elif out == "LOSS":
            out_txt = f'<span style="color:#d73027">باخت {out_pct}%</span>'
        elif out in ("PENDING", "T1_HIT"):
            out_txt = '<span style="color:#2196F3">باز</span>'
        hist_html += f"<tr><td>{t}</td><td>{sym or '-'}</td><td style='color:{c}'>{st}</td><td>{sc or '-'}</td><td>{out_txt}</td></tr>"

    best_opt_html = "-"
    if best_opt:
        try:
            best_opt_html = f"{best_opt[0]} | strike {int(best_opt[1]):,} | قیمت {int(best_opt[2]):,} | {best_opt[3]} روز"
        except Exception:
            best_opt_html = str(best_opt[0]) if best_opt else "-"

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="20">
<title>داشبورد اهرم AI</title>
<style>
  body {{ font-family: Tahoma, sans-serif; background: #0f1115; color: #eee; padding: 20px; margin: 0; }}
  h1 {{ color: #4caf50; font-size: 22px; margin: 0 0 5px; }}
  .updated {{ color: #888; font-size: 12px; margin-bottom: 18px; }}
  .grid {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
  .card {{ background: #1b1e26; border-radius: 10px; padding: 14px 18px; min-width: 150px; border: 1px solid #2a2e38; }}
  .label {{ color: #888; font-size: 12px; margin-bottom: 4px; }}
  .value {{ font-size: 19px; font-weight: bold; }}
  .signal-big {{ font-size: 28px; font-weight: bold; padding: 18px; border-radius: 12px; text-align: center; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; background: #1b1e26; border-radius: 10px; overflow: hidden; margin-bottom: 20px; }}
  td, th {{ padding: 9px 12px; border-bottom: 1px solid #2a2e38; text-align: right; font-size: 13px; }}
  th {{ background: #242834; color: #aaa; }}
  .badge {{ padding: 3px 9px; border-radius: 10px; font-size: 11px; color: #fff; }}
  section {{ margin-bottom: 24px; }}
  h2 {{ font-size: 15px; color: #ccc; border-bottom: 1px solid #2a2e38; padding-bottom: 6px; }}
</style>
</head>
<body>
<h1>🚀 داشبورد نوسان‌گیری اپشن اهرم</h1>
<div class="updated">آخرین به‌روزرسانی: {now_str} (هر ۲۰ ثانیه خودکار)</div>

<div class="signal-big" style="background:{sig_color}; color:#fff;">
  آخرین سیگنال: {sig_fa}
</div>

<div class="grid">
  <div class="card"><div class="label">قیمت اهرم</div><div class="value">{ahrm_price}</div></div>
  <div class="card"><div class="label">بهترین اپشن</div><div class="value" style="font-size:13px">{best_opt_html}</div></div>
  <div class="card"><div class="label">امتیاز آخرین سیگنال</div><div class="value">{last_signal[3] if last_signal and last_signal[3] else '-'}</div></div>
  <div class="card"><div class="label">برد / باخت</div><div class="value">{wins} / {losses} ({win_rate}%)</div></div>
  <div class="card"><div class="label">سیگنال باز</div><div class="value">{pending}</div></div>
</div>

<section>
  <h2>📋 پوزیشن‌های باز (تحت پیگیری)</h2>
  <table>
    <tr><th>نماد</th><th>ورودی</th><th>هدف ۱</th><th>هدف ۲</th><th>حد ضرر</th><th>قیمت فعلی</th><th>سود/زیان</th><th>وضعیت</th></tr>
    {pos_html if pos_html else "<tr><td colspan='8' style='color:#888;text-align:center'>پوزیشن بازی نیست</td></tr>"}
  </table>
</section>

<section>
  <h2>📜 تاریخچه‌ی سیگنال‌ها</h2>
  <table>
    <tr><th>زمان</th><th>نماد</th><th>سیگنال</th><th>امتیاز</th><th>نتیجه</th></tr>
    {hist_html if hist_html else "<tr><td colspan='5' style='color:#888;text-align:center'>هنوز سیگنالی ثبت نشده</td></tr>"}
  </table>
</section>

<section>
  <h2>🧠 وضعیت هوش مصنوعی</h2>
  <div class="grid">
    <div class="card"><div class="label">کل سیگنال‌ها</div><div class="value">{total_sig}</div></div>
    <div class="card"><div class="label">نرخ برد</div><div class="value">{win_rate}%</div></div>
    <div class="card"><div class="label">در انتظار</div><div class="value">{pending}</div></div>
  </div>
  <div style="color:#888;font-size:12px">برای آموزش هوش مصنوعی به حداقل ۲۰ سیگنال ارزیابی‌شده نیاز است. هرچه بیشتر کار کند، دقیق‌تر می‌شود.</div>
</section>

</body>
</html>"""

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print("[DASHBOARD] ERROR:", e)

    return OUTPUT_FILE


if __name__ == "__main__":
    out = generate()
    print(f"داشبورد ساخته شد: {out}")
    print("فایل dashboard.html رو با مرورگر باز کن.")