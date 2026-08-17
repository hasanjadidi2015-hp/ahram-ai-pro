# -*- coding: utf-8 -*-
import sqlite3
import config


def create_database():
    conn = sqlite3.connect(config.DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT,
        last_price REAL,
        closing_price REAL,
        volume REAL,
        trades INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_time TEXT,
        exit_time TEXT,
        entry_price REAL,
        exit_price REAL,
        direction TEXT,
        profit REAL,
        reason_entry TEXT,
        reason_exit TEXT
    )
    """)

    cursor.execute("""
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
        open_interest REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS option_trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_time TEXT,
        exit_time TEXT,
        symbol TEXT,
        stock_price REAL,
        option_price REAL,
        strike_price REAL,
        direction TEXT,
        profit REAL,
        reason_entry TEXT,
        reason_exit TEXT
    )
    """)

    conn.commit()
    conn.close()
    print("=" * 50)
    print("DATABASE READY")
    print("=" * 50)


if __name__ == "__main__":
    create_database()