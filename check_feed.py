# -*- coding: utf-8 -*-
import requests
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.tsetmc.com/"}
URL = "https://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
r = requests.get(URL, headers=HEADERS, timeout=25)
print("http:", r.status_code, "chars:", len(r.text))
rows = r.text.split("@")[2].strip().split(";")
print("rows:", len(rows))
for row in rows:
    if "8032" in row:
        f = row.split(",")
        print("--- len:", len(f))
        for i in (2, 4, 5, 6, 7, 8, 10, 22, 24):
            print(i, "=", f[i] if i < len(f) else "?")
print("DONE")