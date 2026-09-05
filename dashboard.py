# -*- coding: utf-8 -*-
"""
ماژول تولید داشبورد زنده تصمیم‌یار معامله آپشن (Dashboard Engine V4)
نسخه اصلاحی 2026-09-05 (فیکس خطای f-string فرمت عددی)
تولید خروجی dashboard.html با پشتیبانی از تم تاریک و نمایش ۳ نماد اصلی
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Dashboard")

DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db"
}

OUTPUT_HTML_FILE = "dashboard.html"


def fmt_num(val) -> str:
    """تابع کمکی ایمن برای فرمت کردن اعداد (حل خطای f-string)"""
    if isinstance(val, (int, float)):
        return f"{val:,.0f}"
    if val is None or val == "-" or val == "":
        return "-"
    try:
        v = float(val)
        return f"{v:,.0f}"
    except (ValueError, TypeError):
        return str(val) if val is not None else "-"


def get_symbol_data(symbol: str, db_path: str) -> Dict[str, Any]:
    data = {
        "symbol": symbol,
        "db_path": db_path,
        "last_price": 0,
        "closing_price": 0,
        "price_time": "-",
        "signal_type": "WATCH",
        "signal_score": 0,
        "signal_time": "-",
        "option_symbol": "-",
        "option_price": "-",
        "stop_loss": "-",
        "take_profit": "-",
        "qty": "-",
        "recent_signals": []
    }

    if not os.path.exists(db_path):
        return data

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prices';")
        if cursor.fetchone():
            cursor.execute("SELECT last_price, closing_price, time FROM prices ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                data["last_price"] = row["last_price"] or 0
                data["closing_price"] = row["closing_price"] or 0
                data["price_time"] = row["time"] or "-"

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signal_history';")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM signal_history ORDER BY id DESC LIMIT 1")
            last_sig = cursor.fetchone()
            if last_sig:
                d = dict(last_sig)
                data["signal_type"] = d.get("signal_type", "WATCH")
                data["signal_score"] = float(d.get("score", 0.0) or 0.0)
                data["signal_time"] = d.get("time", "-")
                data["option_symbol"] = d.get("option_symbol") or "-"
                data["option_price"] = d.get("option_price") or "-"
                data["stop_loss"] = d.get("stop_loss") or "-"
                data["take_profit"] = d.get("take_profit") or "-"
                data["qty"] = d.get("qty") or "-"

            cursor.execute("SELECT * FROM signal_history ORDER BY id DESC LIMIT 5")
            data["recent_signals"] = [dict(r) for r in cursor.fetchall()]

    except Exception as e:
        logger.warning(f"⚠️ خطا در خواندن داده‌های {symbol}: {e}")
    finally:
        if conn:
            conn.close()

    return data


def generate_html_content(all_data: List[Dict[str, Any]]) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cards_html = ""
    for item in all_data:
        sym = item["symbol"]
        sig = item["signal_type"]
        score = item["signal_score"]
        l_price = item["last_price"]
        opt_sym = item["option_symbol"]
        sl_raw = item["stop_loss"]
        tp_raw = item["take_profit"]
        qty_raw = item["qty"]

        # پیش‌پردازش فرمت عددی (رفع خطای قبلی)
        qty_str = fmt_num(qty_raw)
        sl_str = fmt_num(sl_raw)
        tp_str = fmt_num(tp_raw)
        price_str = fmt_num(l_price)

        # استایل‌بندی
        if sig == "BUY_CALL":
            sig_badge = '<span class="badge badge-call">🟢 خرید کال (BUY_CALL)</span>'
            card_border = "border-call"
        elif sig == "BUY_PUT":
            sig_badge = '<span class="badge badge-put">🔴 خرید پوت (BUY_PUT)</span>'
            card_border = "border-put"
        else:
            sig_badge = '<span class="badge badge-watch">⚪ خنثی / نظاره‌گر (WATCH)</span>'
            card_border = "border-watch"

        if sig in ["BUY_CALL", "BUY_PUT"] and opt_sym not in ["-", None, ""]:
            risk_section = f"""
            <div class="risk-box">
                <div class="risk-title">🛡️ طرح مدیریت ریسک و نوسان‌گیری</div>
                <div class="risk-grid">
                    <div><strong>نماد آپشن:</strong> <span class="highlight">{str(opt_sym)}</span></div>
                    <div><strong>تعداد خرید مجاز:</strong> <span class="highlight">{qty_str}</span> برگه</div>
                    <div><strong>حد سود آپشن (TP):</strong> <span class="text-green">{tp_str} ریال (+40%)</span></div>
                    <div><strong>حد ضرر آپشن (SL):</strong> <span class="text-red">{sl_str} ریال (-20%)</span></div>
                </div>
            </div>
            """
        else:
            risk_section = """
            <div class="risk-box neutral-box">
                <div class="risk-title">☕ مدیریت ریسک: پوزیشنی فعال نیست</div>
                <div style="font-size: 13px; color: #8b949e; margin-top: 5px;">سیستم در حال حاضر پایش بازار را بدون اتخاذ موقعیت ادامه می‌دهد.</div>
            </div>
            """

        cards_html += f"""
        <div class="card {card_border}">
            <div class="card-header">
                <h2>{sym}</h2>
                <div>{sig_badge}</div>
            </div>
            <div class="price-row">
                <div>آخرین قیمت سهم: <strong>{price_str} ریال</strong></div>
                <div>امتیاز استراتژی: <strong>{score:.1f} / 100</strong></div>
            </div>
            {risk_section}
            <div class="time-footer">⏱️ زمان آخرین تحلیل: {str(item.get('signal_time', '-'))}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="20">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>داشبورد تصمیم‌یار آپشن بورس ایران | نسخه V4</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, sans-serif; }}
        body {{ background-color: #0d1117; color: #c9d1d9; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #30363d; }}
        .header h1 {{ font-size: 24px; color: #58a6ff; margin-bottom: 8px; }}
        .header p {{ font-size: 13px; color: #8b949e; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; max-width: 1200px; margin: 0 auto; }}
        .card {{ background-color: #161b22; border-radius: 12px; padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); border: 2px solid transparent; }}
        .border-call {{ border-color: #238636; }}
        .border-put {{ border-color: #da3633; }}
        .border-watch {{ border-color: #30363d; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .card-header h2 {{ font-size: 20px; color: #f0f6fc; }}
        .badge {{ padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
        .badge-call {{ background-color: rgba(35, 134, 54, 0.2); color: #3fb950; border: 1px solid #238636; }}
        .badge-put {{ background-color: rgba(218, 54, 51, 0.2); color: #f85149; border: 1px solid #da3633; }}
        .badge-watch {{ background-color: rgba(139, 148, 158, 0.2); color: #8b949e; border: 1px solid #30363d; }}
        .price-row {{ display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 15px; background: #0d1117; padding: 10px; border-radius: 8px; }}
        .risk-box {{ background: #21262d; border-radius: 8px; padding: 12px; margin-top: 10px; border-left: 4px solid #58a6ff; }}
        .neutral-box {{ border-left: 4px solid #8b949e; }}
        .risk-title {{ font-size: 13px; font-weight: bold; margin-bottom: 8px; color: #58a6ff; }}
        .neutral-box .risk-title {{ color: #8b949e; }}
        .risk-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px; }}
        .highlight {{ color: #e3b341; font-weight: bold; }}
        .text-green {{ color: #3fb950; font-weight: bold; }}
        .text-red {{ color: #f85149; font-weight: bold; }}
        .time-footer {{ font-size: 11px; color: #8b949e; text-align: left; margin-top: 15px; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #8b949e; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 مانیتورینگ زنده معاملات آپشن (اهرم | وبملت | شستا)</h1>
        <p>بروزرسانی خودکار هر ۲۰ ثانیه | آخرین بروزرسانی سیستم: {now_str}</p>
    </div>

    <div class="grid">
        {cards_html}
    </div>

    <div class="footer">
        سیستم تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro) | نسخه نهایی 2026
    </div>
</body>
</html>
"""
    return html


def generate_html(output_file: str = OUTPUT_HTML_FILE) -> str:
    all_data = []
    for sym, db in DBS.items():
        data = get_symbol_data(sym, db)
        all_data.append(data)

    html_content = generate_html_content(all_data)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"✅ فایل داشبورد با موفقیت تولید شد: {output_file}")
    return output_file


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\n=== [تست خودکار ماژول داشبورد V4] ===")
        out = generate_html("dashboard_test.html")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            print(f"🥇 نتیجه تست: پاس شد ✅ (فایل {out} با موفقیت ساخته شد)")
            try: os.remove(out)
            except Exception: pass
        else:
            print("❌ نتیجه تست: ساخت داشبورد با شکست مواجه شد!")
        print("======================================\n")
    else:
        generate_html()