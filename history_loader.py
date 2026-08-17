import sqlite3
import requests
import config

conn = sqlite3.connect(config.DATABASE_NAME)
cur = conn.cursor()

url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{config.INS_CODE}/0"

response = requests.get(url, timeout=20)

if response.status_code != 200:
    print("SERVER ERROR :", response.status_code)
    quit()

data = response.json()["closingPriceDaily"]

count = 0

for row in reversed(data):

    cur.execute("""
    INSERT INTO prices
    (
        time,
        last_price,
        closing_price,
        volume,
        trades
    )
    VALUES (?,?,?,?,?)
    """,
    (
        str(row["dEven"]),
        row["pDrCotVal"],
        row["pClosing"],
        row["qTotTran5J"],
        row["zTotTran"]
    ))

    count += 1

conn.commit()
conn.close()

print("=" * 40)
print("HISTORY LOADED")
print("ROWS :", count)
print("=" * 40)
