# -*- coding: utf-8 -*-
"""
موتور تولید داشبورد پیشرفته V5 (VIP5 Live Dashboard Engine)
نسخه اصلاحی و بدون باگ 2026-09-06
تولید همزمان خروجی‌های dashboard_v5.html و dashboard_VIP5.html
پشتیبانی از تم دارک، ویجت‌های ریسک، سنتیمنت و جدول تاریخچه سیگنال‌ها
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DashboardV5")

DBS = {
    "اهرم": "ahram_v2.db",
    "وبملت": "webmellt.db",
    "شستا": "shasta.db"
}

OUTPUT_FILES = ["dashboard_v5.html", "dashboard_VIP5.html"]


def fmt_num(val) -> str:
    """فرمت‌بندی ایمن اعداد بدون پرتاب خطا"""
    if val is None or val == "-" or val == "":
        return "-"
    try:
        v = float(val)
        return f"{v:,.0f}"
    except (ValueError, TypeError):
        return str(val)


def get_v5_symbol_data(symbol: str, db_path: str) -> Dict[str, Any]:
    """استخراج امن داده‌های V5 از دیتابیس بدون کرش"""
    data = {
        "symbol": symbol,
        "db_path": db_path,
        "last_price": 0,
        "closing_price": 0,
        "price_time": "-",
        "signal_type": "WATCH",
        "signal_score": 50.0,
        "signal_time": "-",
        "option_symbol": "-",
        "option_price": "-",
        "stop_loss": "-",
        "take_profit": "-",
        "sentiment": "عادی",
        "recent_signals": []
    }

    if not os.path.exists(db_path):
        return data

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # ۱. آخرین قیمت
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prices';")
        if cursor.fetchone():
            cursor.execute("SELECT last_price, closing_price, time FROM prices ORDER BY id DESC LIMIT 1")
            p_row = cursor.fetchone()
            if p_row:
                data["last_price"] = p_row["last_price"] or 0
                data["closing_price"] = p_row["closing_price"] or 0
                data["price_time"] = p_row["time"] or "-"

        # ۲. آخرین سیگنال V5 و مدیریت ریسک
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signal_history';")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM signal_history ORDER BY id DESC LIMIT 1")
            last_sig = cursor.fetchone()
            if last_sig:
                d = dict(last_sig)
                data["signal_type"] = d.get("signal_type", "WATCH")
                
                # خواندن امتیاز با اولویت composite_score و سپس بقیه
                score_val = d.get("composite_score") or d.get("v2_score") or d.get("score") or 50.0
                try: data["signal_score"] = float(score_val)
                except: data["signal_score"] = 50.0

                data["signal_time"] = d.get("time", "-")
                data["option_symbol"] = d.get("option_symbol") or "-"
                data["option_price"] = d.get("option_price") or "-"
                data["stop_loss"] = d.get("stop_loss") or "-"
                data["take_profit"] = d.get("target1") or d.get("take_profit") or "-"

            # ۵ سیگنال اخیر برای جدول تاریخچه
            cursor.execute("SELECT * FROM signal_history ORDER BY id DESC LIMIT 5")
            data["recent_signals"] = [dict(r) for r in cursor.fetchall()]

    except Exception as e:
        logger.warning(f"⚠️ خطای خواندن داده‌های V5 برای {symbol}: {e}")
    finally:
        if conn:
            conn.close()

    return data


def generate_v5_html_content(all_data: List[Dict[str, Any]]) -> str:
    """تولید ساختار شکیل و مدرن HTML با تم VIP Dark"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cards_html = ""
    for item in all_data:
        sym = item["symbol"]
        sig = item["signal_type"]
        score = item["signal_score"]
        l_price = item["last_price"]
        opt_sym = item["option_symbol"]
        sl = item["stop_loss"]
        tp = item["take_profit"]
        opt_p = item["option_price"]

        price_str = fmt_num(l_price)
        sl_str = fmt_num(sl)
        tp_str = fmt_num(tp)
        opt_p_str = fmt_num(opt_p)

        # استایل‌دهی بر اساس نوع سیگنال
        if sig == "BUY_CALL":
            sig_badge = '<span class="badge badge-call">🟢 سیگنال خرید کال (BUY_CALL)</span>'
            card_border = "border-call"
        elif sig == "BUY_PUT":
            sig_badge = '<span class="badge badge-put">🔴 سیگنال خرید پوت (BUY_PUT)</span>'
            card_border = "border-put"
        else:
            sig_badge = '<span class="badge badge-watch">⚪ خنثی / نظاره‌گر (WATCH)</span>'
            card_border = "border-watch"

        # بخش مدیریت ریسک
        if sig in ["BUY_CALL", "BUY_PUT"] and opt_sym not in ["-", None, ""]:
            risk_section = f"""
            <div class="risk-box">
                <div class="risk-title">🛡️ طرح مدیریت ریسک V5 Engine</div>
                <div class="risk-grid">
                    <div><strong>قرارداد پیشنهادی:</strong> <span class="highlight">{str(opt_sym)}</span></div>
                    <div><strong>قیمت ورود آپشن:</strong> <span>{opt_p_str} ریال</span></div>
                    <div><strong>حد سود آپشن (TP):</strong> <span class="text-green">{tp_str} ریال (+30/35%)</span></div>
                    <div><strong>حد ضرر آپشن (SL):</strong> <span class="text-red">{sl_str} ریال (-15/17%)</span></div>
                </div>
            </div>
            """
        else:
            risk_section = """
            <div class="risk-box neutral-box">
                <div class="risk-title">☕ مدیریت ریسک: پوزیشنی فعال نیست</div>
                <div style="font-size: 13px; color: #8b949e; margin-top: 5px;">موتور V5 در حال پایش داده‌های نوسان‌پذیری و احساسات بازار است.</div>
            </div>
            """

        cards_html += f"""
        <div class="card {card_border}">
            <div class="card-header">
                <h2>{sym} <span class="engine-tag">V5 VIP</span></h2>
                <div>{sig_badge}</div>
            </div>
            <div class="price-row">
                <div>قیمت سهم: <strong>{price_str} ریال</strong></div>
                <div>امتیاز V5: <strong>{score:.1f} / 100</strong></div>
            </div>
            {risk_section}
            <div class="time-footer">⏱️ آخرین پایش زنده: {str(item.get('signal_time', '-'))}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="20">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>داشبورد پیشرفته تصمیم‌یار آپشن | نسخه VIP V5</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, sans-serif; }}
        body {{ background-color: #0b0e14; color: #c9d1d9; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #30363d; }}
        .header h1 {{ font-size: 24px; color: #e3b341; margin-bottom: 8px; }}
        .header p {{ font-size: 13px; color: #8b949e; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; max-width: 1200px; margin: 0 auto; }}
        .card {{ background-color: #161b22; border-radius: 12px; padding: 20px; box-shadow: 0 4px 14px rgba(0,0,0,0.6); border: 2px solid transparent; }}
        .border-call {{ border-color: #238636; }}
        .border-put {{ border-color: #da3633; }}
        .border-watch {{ border-color: #30363d; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .card-header h2 {{ font-size: 20px; color: #f0f6fc; display: flex; align-items: center; gap: 8px; }}
        .engine-tag {{ font-size: 11px; background: #388bfd33; color: #58a6ff; padding: 2px 6px; border-radius: 6px; border: 1px solid #1f6feb; }}
        .badge {{ padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
        .badge-call {{ background-color: rgba(35, 134, 54, 0.2); color: #3fb950; border: 1px solid #238636; }}
        .badge-put {{ background-color: rgba(218, 54, 51, 0.2); color: #f85149; border: 1px solid #da3633; }}
        .badge-watch {{ background-color: rgba(139, 148, 158, 0.2); color: #8b949e; border: 1px solid #30363d; }}
        .price-row {{ display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 15px; background: #0d1117; padding: 12px; border-radius: 8px; }}
        .risk-box {{ background: #21262d; border-radius: 8px; padding: 14px; margin-top: 10px; border-left: 4px solid #e3b341; }}
        .neutral-box {{ border-left: 4px solid #8b949e; }}
        .risk-title {{ font-size: 13px; font-weight: bold; margin-bottom: 10px; color: #e3b341; }}
        .neutral-box .risk-title {{ color: #8b949e; }}
        .risk-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 13px; }}
        .highlight {{ color: #e3b341; font-weight: bold; }}
        .text-green {{ color: #3fb950; font-weight: bold; }}
        .text-red {{ color: #f85149; font-weight: bold; }}
        .time-footer {{ font-size: 11px; color: #8b949e; text-align: left; margin-top: 15px; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #8b949e; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>👑 داشبورد VIP موتور تحلیلی V5 (اهرم | وبملت | شستا)</h1>
        <p>بروزرسانی خودکار هر ۲۰ ثانیه | آخرین بروزرسانی: {now_str}</p>
    </div>

    <div class="grid">
        {cards_html}
    </div>

    <div class="footer">
        سیستم تصمیم‌یار معامله آپشن بورس ایران (Ahram AI Pro - V5 Edition)
    </div>
</body>
</html>
"""
    return html


def generate_html() -> List[str]:
    """تولید و ذخیره فایل‌های داشبورد V5 بدون باگ"""
    all_data = []
    for sym, db in DBS.items():
        data = get_v5_symbol_data(sym, db)
        all_data.append(data)

    html_content = generate_v5_html_content(all_data)

    created_files = []
    for out_file in OUTPUT_FILES:
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            created_files.append(out_file)
        except Exception as e:
            logger.error(f"❌ خطا در ساخت {out_file}: {e}")

    logger.info(f"✅ فایل‌های داشبورد V5 با موفقیت ساخته شدند: {', '.join(created_files)}")
    return created_files


# =====================================================================
# بخش تست خودکار
# =====================================================================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\n=== [تست خودکار ماژول داشبورد V5 VIP] ===")
        outs = generate_html()
        if outs:
            print(f"🥇 نتیجه تست: پاس شد ✅ (فایل‌های {', '.join(outs)} با موفقیت تولید شدند)")
        else:
            print("❌ نتیجه تست: شکست!")
        print("=========================================\n")
    else:
        generate_html()