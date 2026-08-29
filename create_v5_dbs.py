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
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS order_book (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT,
        buy_price REAL,
        sell_price REAL,
        buy_volume REAL,
        sell_volume REAL
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_date TEXT,
        title TEXT,
        category TEXT,
        source TEXT
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS iv_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        atm_iv REAL
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS max_pain_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expiry TEXT,
        stock_price REAL,
        max_pain_strike REAL,
        current_distance_pct REAL,
        data_quality TEXT,
        contracts_count INTEGER,
        contracts_with_oi INTEGER,
        time TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print(f"✅ {db_path} ready - tables created")

print("\nAll V5 DBs ready")
