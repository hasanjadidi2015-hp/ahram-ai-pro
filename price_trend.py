# -*- coding: utf-8 -*-
import sqlite3
con = sqlite3.connect("file:ahram_v2.db?mode=ro", uri=True)
cur = con.cursor()
cur.execute("SELECT symbol, time, option_price FROM options WHERE symbol LIKE '%8032%' AND time LIKE '2026-09-28%' ORDER BY time ASC")
rows = cur.fetchall()
print("rows today:", len(rows))
print("min:", min(x[2] for x in rows), "max:", max(x[2] for x in rows))
print("--- first 3 ---")
for r in rows[:3]:
    print(r)
print("--- last 8 ---")
for r in rows[-8:]:
    print(r)
con.close()
print("DONE")