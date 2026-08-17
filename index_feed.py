import sqlite3
from datetime import datetime

import algotik_tse as att

import config


def create_index_table():

    conn = sqlite3.connect(config.DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            index_name TEXT,
            value REAL,
            change_pct REAL
        )
        """
    )

    conn.commit()
    conn.close()


def fetch_and_save_indices():

    create_index_table()

    try:

        all_indices = att.list_indices()

    except Exception as e:

        print("INDEX FETCH ERROR:", e)
        return None

    wanted = {

        "شاخص کل": {

            "ins_code": "32097828799138957",

            "value": None

        },

        "شاخص کل هم وزن": {

            "ins_code": "67130298613737946",

            "value": None

        }

    }

    for name, info in wanted.items():

        row = all_indices[
            all_indices["InsCode"].astype(str) == info["ins_code"]
        ]

        if row.empty:
            continue

        change = float(row.iloc[0]["Change"])
        value = float(row.iloc[0]["Value"])

        computed_pct = None

        if (value - change) != 0:

            computed_pct = (change / (value - change)) * 100

        # شاخص در یک روز معمولاً بیش از چند درصد تغییر نمی‌کند
        # اگر عدد نامعقول بود، بی‌خیال درصد می‌شویم تا گمراه‌کننده نباشد
        if computed_pct is not None and abs(computed_pct) > 20:
            computed_pct = None

        info["value"] = {

            "value": value,

            "change_pct": computed_pct

        }

    wanted = {
        name: info["value"]
        for name, info in wanted.items()
    }

    conn = sqlite3.connect(config.DATABASE_NAME)
    cursor = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for name, data in wanted.items():

        if data is None:
            continue

        cursor.execute(
            """
            INSERT INTO indices
            (time, index_name, value, change_pct)
            VALUES (?, ?, ?, ?)
            """,
            (now, name, data["value"], data["change_pct"])
        )

    conn.commit()
    conn.close()

    return wanted


if __name__ == "__main__":

    result = fetch_and_save_indices()
    print(result)