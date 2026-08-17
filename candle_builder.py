import sqlite3

import pandas as pd

import config


def load_tick_data(end_time=None):

    conn = sqlite3.connect(config.DATABASE_NAME)

    df = pd.read_sql(
        "SELECT time, last_price FROM prices ORDER BY id",
        conn
    )

    conn.close()

    # جدول prices ممکن است شامل داده‌ی تاریخی قدیمی با فرمت متفاوت
    # باشد. فقط فرمت شناخته‌شده‌ی زنده را قطعی پردازش می‌کنیم
    parsed = pd.to_datetime(
        df["time"],
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce"
    )

    valid_mask = parsed.notna()

    df = df[valid_mask].copy()
    df["time"] = parsed[valid_mask]

    if end_time is not None:
        df = df[df["time"] <= end_time]

    return df


def build_candles(minutes=15, df=None, end_time=None):

    if df is None:
        df = load_tick_data(end_time=end_time)

    elif end_time is not None:
        df = df[df["time"] <= end_time]

    if df.empty or len(df) < 2:
        return pd.DataFrame()

    series = df.set_index("time")["last_price"]

    ohlc = series.resample(f"{minutes}min").ohlc()

    ohlc = ohlc.dropna()

    return ohlc.reset_index()


if __name__ == "__main__":

    candles = build_candles(minutes=15)

    print(candles.tail(10))