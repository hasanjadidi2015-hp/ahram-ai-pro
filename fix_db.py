import sqlite3

for db in ["ahram_v2.db", "webmellt.db", "shasta.db"]:
    try:
        conn = sqlite3.connect(db)
        c = conn.cursor()
        c.execute("PRAGMA table_info(signal_history)")
        cols = [r[1] for r in c.fetchall()]
        if "details" not in cols:
            c.execute("ALTER TABLE signal_history ADD COLUMN details TEXT")
            print(f"{db}: اصلاح شد ✅")
        else:
            print(f"{db}: قبلاً اصلاح شده ✅")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"{db}: خطا - {e}")