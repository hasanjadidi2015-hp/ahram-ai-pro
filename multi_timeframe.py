from candle_builder import build_candles


def calculate_multi_timeframe(candle_minutes=15, min_candles=25, end_time=None):

    candles = build_candles(minutes=candle_minutes, end_time=end_time)

    if candles.empty or len(candles) < min_candles:
        return "NEUTRAL"

    close = candles["close"]

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    if ema9.iloc[-1] > ema21.iloc[-1]:
        return "BULLISH"

    if ema9.iloc[-1] < ema21.iloc[-1]:
        return "BEARISH"

    return "NEUTRAL"


if __name__ == "__main__":

    print(calculate_multi_timeframe())