# -*- coding: utf-8 -*-
"""AHRAM SYMBOLS UTILS - کد ins_code نمادها را خودکار از TSETMC پیدا می‌کند."""
import os
import json
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.tsetmc.com/",
}
SEARCH_URL = "https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{}"
CACHE_FILE = "symbols_cache.json"


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _extract_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


def resolve_ins_code(name):
    """کد ins_code نماد را پیدا می‌کند (ابتدا کش، بعد آنلاین)."""
    cache = _load_cache()
    if cache.get(name):
        return cache[name]
    try:
        r = requests.get(SEARCH_URL.format(name), headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception as e:
        print(f"[SYMBOLS] خطا در حل کد {name}:", e)
        return None

    items = _extract_items(data)
    for it in items:
        if not isinstance(it, dict):
            continue
        sym = (it.get("symbol") or it.get("lVal18AFC") or it.get("Symbol") or "").strip()
        full = (it.get("name") or it.get("lVal30") or it.get("Name") or "")
        code = str(it.get("insCode") or it.get("InsCode") or it.get("inscode") or "")
        if not code:
            continue
        if sym == name and ("اختیار" not in full and "اختيار" not in full and "حق تقدم" not in full):
            cache[name] = code
            _save_cache(cache)
            return code
    for it in items:
        if not isinstance(it, dict):
            continue
        full = (it.get("name") or it.get("lVal30") or it.get("Name") or "")
        code = str(it.get("insCode") or it.get("InsCode") or "")
        if code and "اختیار" not in full and "اختيار" not in full:
            cache[name] = code
            _save_cache(cache)
            return code
    return None


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for n in ["اهرم", "وبملت", "شستا"]:
        print(f"{n}: {resolve_ins_code(n)}")