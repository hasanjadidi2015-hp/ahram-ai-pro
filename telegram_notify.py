# -*- coding: utf-8 -*-
"""ارسال امن پیام تلگرام با timeout کوتاه."""

import requests

from telegram_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_message(text):
    """ارسال پیام و برگرداندن True/False بدون متوقف‌کردن ربات."""

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM] ERROR: TOKEN یا CHAT_ID تنظیم نشده است.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": str(text)[:4000],
    }

    try:
        response = requests.post(
            url,
            json=data,
            timeout=(3, 5),
        )

        if response.status_code == 200:
            return True

        print(
            "[TELEGRAM] ERROR: "
            f"HTTP {response.status_code} | "
            f"{response.text[:300]}"
        )
        return False

    except requests.exceptions.Timeout:
        print("[TELEGRAM] ERROR: Timeout در اتصال به تلگرام.")
        return False

    except requests.exceptions.RequestException as e:
        print("[TELEGRAM] ERROR:", e)
        return False

    except Exception as e:
        print("[TELEGRAM] UNEXPECTED ERROR:", e)
        return False


if __name__ == "__main__":
    ok = send_telegram_message("🤖 تست تلگرام — AHRAM AI")

    print("OK" if ok else "FAIL")