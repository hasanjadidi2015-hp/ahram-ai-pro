"""
اتصال نمایشی داده AHRAM به نسخه کاری داشبورد VIP

این اسکریپت فقط یک فایل خروجی جدید می‌سازد و فایل‌های اصلی را تغییر نمی‌دهد.
ورودی‌ها:
  options_dashboard_AHRAM.html
  ahram_strategy_data.json
خروجی:
  options_dashboard_AHRAM_LIVE.html
"""

import json
import os
from html import escape

TEMPLATE = "options_dashboard_AHRAM.html"
DATA_FILE = "ahram_strategy_data.json"
OUTPUT = "options_dashboard_AHRAM_LIVE.html"


def fmt(value):
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return escape(str(value))


def pct(value):
    if value is None:
        return "—"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "—"


def make_panel(payload):
    cards = []
    for name, data in payload.get("symbols", {}).items():
        if not data.get("available"):
            cards.append(
                f'<article class="ahram-card"><h3>{escape(name)}</h3>'
                '<div class="ahram-muted">داده دیتابیس در دسترس نیست</div></article>'
            )
            continue

        price = data.get("price") or {}
        signal = data.get("signal") or {}
        max_pain = data.get("max_pain") or []
        latest_mp = max_pain[0] if max_pain else {}
        signal_type = signal.get("signal_type") or "—"
        score = signal.get("score")
        options_count = len(data.get("options") or [])

        mp_line = "Max Pain: —"
        if latest_mp:
            mp_line = (
                f"Max Pain: {fmt(latest_mp.get('max_pain_strike'))} "
                f"· فاصله {pct(latest_mp.get('distance_pct'))}"
            )

        cards.append(
            f'''<article class="ahram-card">
              <div class="ahram-card-title"><h3>{escape(name)}</h3>
              <span class="ahram-signal">{escape(str(signal_type))}</span></div>
              <div class="ahram-price">{fmt(price.get('last_price'))}<small>ریال</small></div>
              <div class="ahram-row">امتیاز <b>{fmt(score)}</b></div>
              <div class="ahram-row">زنجیره آخر <b>{options_count} قرارداد</b></div>
              <div class="ahram-row">{escape(mp_line)}</div>
              <div class="ahram-row ahram-muted">زمان قیمت: {escape(str(price.get('time') or '—'))}</div>
            </article>'''
        )

    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # جلوگیری از بسته‌شدن ناخواسته تگ script در داده‌های متنی
    payload_json = payload_json.replace("<", "\\u003c")

    return f'''<section id="ahram-bridge-panel" dir="rtl">
      <div class="ahram-head">
        <div><h2>🔗 داده واقعی AHRAM AI</h2>
        <p>اتصال نمایشی و فقط‌خواندنی · بدون اثر بر سیگنال‌ها و محاسبات استراتژی</p></div>
        <span class="ahram-readonly">READ ONLY</span>
      </div>
      <div class="ahram-grid">{"".join(cards)}</div>
      <div class="ahram-note">این پنل فقط داده AHRAM را کنار داشبورد استراتژی نشان می‌دهد. انتخاب یا اجرای معامله همچنان باید با بررسی دستی انجام شود.</div>
      <script id="ahram-bridge-data">window.AHRAM_BRIDGE_DATA = {payload_json};</script>
    </section>'''


def main():
    if not os.path.exists(TEMPLATE):
        raise FileNotFoundError(f"فایل قالب پیدا نشد: {TEMPLATE}")
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"فایل داده پیدا نشد: {DATA_FILE}")

    with open(TEMPLATE, "r", encoding="utf-8") as file:
        template = file.read()
    with open(DATA_FILE, "r", encoding="utf-8") as file:
        payload = json.load(file)

    if "</body>" not in template.lower():
        raise ValueError("قالب HTML تگ پایان body ندارد")

    panel = make_panel(payload)
    style = '''<style>
#ahram-bridge-panel{margin:24px auto;padding:20px;max-width:1440px;background:linear-gradient(180deg,#17263d,#111c2e);border:1px solid #2b405e;border-radius:18px;color:#edf3ff;font-family:Tahoma,Arial,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.2)}
#ahram-bridge-panel .ahram-head{display:flex;justify-content:space-between;align-items:center;gap:14px;border-bottom:1px solid #2b405e;padding-bottom:14px;margin-bottom:14px}
#ahram-bridge-panel h2{margin:0 0 5px;font-size:19px}#ahram-bridge-panel h3{margin:0;font-size:16px}
#ahram-bridge-panel p{margin:0;color:#94a3b8;font-size:12px}.ahram-readonly{background:#163a56;color:#7dd3fc;border-radius:999px;padding:7px 11px;font-size:11px;font-weight:bold}
.ahram-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.ahram-card{background:#0d1829;border:1px solid #2b405e;border-radius:13px;padding:14px}.ahram-card-title{display:flex;justify-content:space-between;align-items:center;gap:8px}.ahram-signal{background:#123c29;color:#86efac;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:bold}.ahram-price{font-size:26px;font-weight:900;margin:14px 0 8px}.ahram-price small{font-size:11px;color:#94a3b8;margin-right:5px}.ahram-row{border-top:1px solid #263750;padding:8px 0;color:#b6c4d8;font-size:12px}.ahram-row b{float:left;color:#edf3ff}.ahram-muted{color:#94a3b8;font-size:11px}.ahram-note{margin-top:14px;padding:11px;background:#2b2411;color:#fcd34d;border:1px solid #66501a;border-radius:10px;font-size:12px}
@media(max-width:850px){.ahram-grid{grid-template-columns:1fr}.ahram-head{align-items:flex-start;flex-direction:column}}
</style>'''

    lower = template.lower()
    insert_at = lower.rfind("</body>")
    output = template[:insert_at] + style + panel + template[insert_at:]
    with open(OUTPUT, "w", encoding="utf-8") as file:
        file.write(output)

    print("✅ نسخه نمایشی AHRAM ساخته شد")
    print("OUTPUT:", OUTPUT)
    print("ORIGINAL_UNCHANGED:", TEMPLATE)
    print("READ_ONLY_PANEL: True")


if __name__ == "__main__":
    main()
