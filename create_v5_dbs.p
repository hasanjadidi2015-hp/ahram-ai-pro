# -*- coding: utf-8 -*-
import sqlite3, os

dbs = ["ahram_v2_v5.db", "webmellt_v5.db", "shasta_v5.db"]

for db_path in dbs:
    # اگر وجود دارد پاک کن برای شروع تمیز (اختیاری - کامنت کن اگر نمی‌خوای)
    # if os.path.exists(db_path):
    #     os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS prices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT,
        last_price REAL,
        closing_price REAL,
        volume REAL,
        trades INTEGER
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS options(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT,
        symbol TEXT,
        option_type TEXT,
        stock_price REAL,
        option_price REAL,
        strike_price REAL,
        expire_date TEXT,
        days_to_expire INTEGER,
        volume REAL,
        value_traded REAL,
        open_interest REAL,
        implied_volatility REAL,
        delta REAL,
        gamma REAL,
        theta REAL,
        vega REAL
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS signal_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT,
        symbol TEXT,
        signal_type TEXT,
        composite_score REAL,
        option_symbol TEXT,
        option_price REAL,
        strike_price REAL,
        stop_loss REAL,
        target1 REAL,
        target2 REAL,
        outcome TEXT DEFAULT 'PENDING',
        outcome_pct REAL DEFAULT 0,
        details TEXT,
        position_id TEXT,
        v2_score REAL,
        v2_decision TEXT,
        v2_best_symbol TEXT
    )
    """)
    
    # نکته: order_book / daily_news / max_pain_history عمداً اینجا ساخته
    # نمی‌شن -- ماژول‌های خودشون (order_book.py, daily_news.py, max_pain.py)
    # مالک واقعی این جدول‌هان و شِمای درست و به‌روزشون رو خودشون موقع اولین
    # استفاده می‌سازن/خودترمیم می‌کنن. اگه اینجا با یه شِمای ناقص/قدیمی از
    # قبل ساخته بشن، CREATE TABLE IF NOT EXISTS اون ماژول‌ها هیچ کاری نمی‌کنه
    # (چون جدول از قبل هست) و بعضی‌هاشون (مثل max_pain.py) خودترمیم ALTER
    # هم ندارن -- یعنی اولین INSERT با خطای "no such column" کرش می‌کنه.

    conn.commit()
    conn.close()
    print(f"✅ {db_path} ready - tables created")

print("\nAll V5 DBs ready")