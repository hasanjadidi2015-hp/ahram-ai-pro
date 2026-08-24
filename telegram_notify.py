# -*- coding: utf-8 -*-
"""ارسال پیام به تلگرام"""
import requests
from datetime import datetime, timedelta
from telegram_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# اگه تلگرام چندبار پشت سر هم fail کنه (مثلاً فیلترینگ)، دیگه تا مدتی
# تلاش نمی‌کنیم -- وگرنه هر بار ۱۰ ثانیه تایم‌اوت هدر می‌ره و کل سیکل رو
# کند می‌کنه.
_consecutive_failures = 0
_circuit_open_until = None
_FAILURE_THRESHOLD = 3
_COOLDOWN_MINUTES = 10


def send_telegram_message(text):
    global _consecutive_failures, _circuit_open_until
    now = datetime.now()
    if _circuit_open_until and now < _circuit_open_until:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]}
        r = requests.post(url, json=data, timeout=10)
        ok = r.status_code == 200
        if ok:
            _consecutive_failures = 0
            _circuit_open_until = None
        else:
            _consecutive_failures += 1
        return ok
    except Exception as e:
        print("[TELEGRAM] ERROR:", e)
        _consecutive_failures += 1
        if _consecutive_failures >= _FAILURE_THRESHOLD:
            _circuit_open_until = now + timedelta(minutes=_COOLDOWN_MINUTES)
            print(
                f"[TELEGRAM] {_consecutive_failures} خطای پیاپی -- تا "
                f"{_circuit_open_until.strftime('%H:%M')} موقتاً تلاش نمی‌کنیم"
            )
        return False

if __name__ == "__main__":
    ok = send_telegram_message("🤖 تست تلگرام — ربات اهرم")
    print("OK" if ok else "FAIL")