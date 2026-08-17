# -*- coding: utf-8 -*-
"""ارسال پیام به تلگرام"""
import requests
from telegram_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]}
        r = requests.post(url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print("[TELEGRAM] ERROR:", e)
        return False

if __name__ == "__main__":
    ok = send_telegram_message("🤖 تست تلگرام — ربات اهرم")
    print("OK" if ok else "FAIL")