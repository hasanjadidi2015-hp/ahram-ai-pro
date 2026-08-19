# -*- coding: utf-8 -*-
"""
AHRAM DASHBOARD v5 - کامل با جزئیات آپشن
"""
import sqlite3
import os
from datetime import datetime

OUTPUT_FILE = "dashboard.html"

DBS = [
    ("اهرم", "ahram_v2.db"),
    ("وبملت", "webmellt.db"),
    ("شستا", "shasta.db"),
]


def get_price(db):
    try:
        if not os.path.exists(db):
            return "-"
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT last_price FROM prices WHERE last_price>0 ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        conn.close()
        return f"{int(float(r[0])):,}" if r else "-"
    except:
        return "-"


def get_signals(db, limit=10):
    try:
        if not os.path.exists(db):
            return []
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT time, signal_type, composite_score, option_symbol, option_price, strike_price, stop_loss, target1, target2, details FROM signal_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        return rows
    except:
        return []


def fmt(val):
    """فرمت عدد با جداکننده"""
    if val is None:
        return "-"
    try:
        return f"{int(float(val)):,}"
    except:
        return "-"


def generate():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    all_data = []
    all_signals = []
    
    for name, db in DBS:
        price = get_price(db)
        signals = get_signals(db, 10)
        all_data.append({"name": name, "price": price, "signals": signals})
        for s in signals:
            all_signals.append((name, s))
    
    all_signals.sort(key=lambda x: x[1][0] or "", reverse=True)
    all_signals = all_signals[:20]
    
    latest_buy = None
    for name, s in all_signals:
        if s[1] and "BUY" in s[1]:
            latest_buy = (name, s)
            break
    
    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="30">
<title>AHRAM AI Dashboard</title>
<style>
body {{ font-family: Tahoma; background: #0a0a1a; color: #eee; padding: 20px; margin: 0; }}
h1 {{ color: #00d4ff; text-align: center; margin-bottom: 5px; }}
h2 {{ color: #aaa; border-bottom: 1px solid #333; padding-bottom: 8px; margin-top: 30px; }}
.subtitle {{ text-align: center; color: #666; margin-bottom: 20px; }}
.cards {{ display: flex; gap: 15px; flex-wrap: wrap; justify-content: center; margin: 20px 0; }}
.card {{ background: #16213e; border: 1px solid #0f3460; border-radius: 12px; padding: 20px; min-width: 220px; text-align: center; }}
.card h3 {{ color: #00d4ff; margin: 0 0 10px; font-size: 18px; }}
.card .price {{ font-size: 32px; font-weight: bold; color: #fff; }}
.card .unit {{ font-size: 12px; color: #888; }}
.signal-box {{ background: #16213e; border: 2px solid #4caf50; border-radius: 12px; padding: 20px; margin: 20px 0; }}
.signal-box.sell {{ border-color: #f44336; }}
.signal-box.watch {{ border-color: #ff9800; }}
.signal-title {{ font-size: 24px; font-weight: bold; margin-bottom: 15px; }}
.signal-title.buy {{ color: #4caf50; }}
.signal-title.sell {{ color: #f44336; }}
.signal-title.watch {{ color: #ff9800; }}
.signal-details {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.signal-detail {{ background: #1a1a2e; padding: 10px; border-radius: 8px; }}
.signal-detail .label {{ color: #888; font-size: 12px; }}
.signal-detail .value {{ color: #fff; font-size: 16px; font-weight: bold; }}
table {{ width: 100%; border-collapse: collapse; background: #16213e; border-radius: 8px; overflow: hidden; }}
th {{ background: #0f3460; padding: 12px; text-align: right; font-size: 13px; }}
td {{ padding: 10px; border-bottom: 1px solid #1a1a2e; font-size: 13px; }}
.buy {{ color: #4caf50; font-weight: bold; }}
.sell {{ color: #f44336; font-weight: bold; }}
.watch {{ color: #ff9800; }}
.updated {{ text-align: center; color: #666; font-size: 12px; margin-top: 30px; }}
</style>
</head>
<body>
<h1>🚀 AHRAM AI Dashboard</h1>
<p class="subtitle">سیستم معامله‌گری آپشن بورس ایران</p>

<h2>📊 نمادها</h2>
<div class="cards">
"""
    
    for d in all_data:
        html += f"""
<div class="card">
  <h3>{d['name']}</h3>
  <div class="price">{d['price']}</div>
  <div class="unit">ریال</div>
</div>
"""
    
    html += "</div>"
    
    if latest_buy:
        name, s = latest_buy
        time_val, sig_type, score, opt_sym, opt_price, strike, sl, t1, t2, details = s
        
        color_class = "buy" if "BUY" in (sig_type or "") else ("sell" if "SELL" in (sig_type or "") else "watch")
        sig_fa = {"BUY_CALL": "🟢 سیگنال خرید کال", "BUY_PUT": "🔴 سیگنال خرید پوت", "BUY": "🟢 سیگنال خرید"}.get(sig_type, sig_type)
        
        html += f"""
<h2>🎯 آخرین سیگنال آپشن</h2>
<div class="signal-box {color_class}">
  <div class="signal-title {color_class}">{sig_fa}</div>
  <div class="signal-details">
    <div class="signal-detail">
      <div class="label">نماد پایه</div>
      <div class="value">{name}</div>
    </div>
    <div class="signal-detail">
      <div class="label">زمان</div>
      <div class="value">{time_val}</div>
    </div>
    <div class="signal-detail">
      <div class="label">امتیاز</div>
      <div class="value">{score}/100</div>
    </div>
    <div class="signal-detail">
      <div class="label">قرارداد آپشن</div>
      <div class="value">{opt_sym or '-'}</div>
    </div>
    <div class="signal-detail">
      <div class="label">قیمت آپشن</div>
      <div class="value">{fmt(opt_price)}</div>
    </div>
    <div class="signal-detail">
      <div class="label">Strike</div>
      <div class="value">{fmt(strike)}</div>
    </div>
    <div class="signal-detail">
      <div class="label">حد ضرر</div>
      <div class="value" style="color:#f44336">{fmt(sl)}</div>
    </div>
    <div class="signal-detail">
      <div class="label">هدف اول</div>
      <div class="value" style="color:#4caf50">{fmt(t1)}</div>
    </div>
    <div class="signal-detail">
      <div class="label">هدف دوم</div>
      <div class="value" style="color:#4caf50">{fmt(t2)}</div>
    </div>
  </div>
</div>
"""
    else:
        html += """
<h2>🎯 آخرین سیگنال آپشن</h2>
<div class="signal-box watch">
  <div class="signal-title watch">هنوز سیگنال آپشن صادر نشده</div>
  <p style="color:#888;">سیستم منتظر شرایط مناسب است...</p>
</div>
"""
    
    html += """
<h2>📋 تاریخچه سیگنال‌ها</h2>
<table>
<tr><th>نماد</th><th>زمان</th><th>سیگنال</th><th>امتیاز</th><th>آپشن</th><th>Strike</th><th>قیمت آپشن</th></tr>
"""
    
    for name, s in all_signals:
        time_val, sig_type, score, opt_sym, opt_price, strike, sl, t1, t2, details = s
        color = "buy" if "BUY" in (sig_type or "") else ("sell" if "SELL" in (sig_type or "") else "watch")
        sig_fa = {"BUY_CALL": "🟢 خرید کال", "BUY_PUT": "🔴 خرید پوت", "BUY": "🟢 خرید", "SELL": "🔴 فروش", "WATCH": "🟡 تحت نظر", "WAIT": "⚪ صبر"}.get(sig_type, sig_type)
        
        html += f'<tr><td><b>{name}</b></td><td>{time_val or "-"}</td><td class="{color}">{sig_fa}</td><td>{score or "-"}</td><td>{opt_sym or "-"}</td><td>{fmt(strike)}</td><td>{fmt(opt_price)}</td></tr>\n'
    
    if not all_signals:
        html += '<tr><td colspan="7" style="text-align:center;color:#666;">هنوز سیگنالی ثبت نشده</td></tr>\n'
    
    html += f"""
</table>

<div class="updated">آخرین بروزرسانی: {now}</div>
</body>
</html>"""
    
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        return OUTPUT_FILE
    except Exception as e:
        print(f"[DASHBOARD] ERROR: {e}")
        return None


if __name__ == "__main__":
    out = generate()
    if out:
        print(f"✅ داشبورد ساخته شد: {out}")
