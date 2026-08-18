# -*- coding: utf-8 -*-
"""
AHRAM AI - BACKTEST ENGINE
بک‌تست با دیتای محلی دیتابیس
"""
import sys
import sqlite3
import math
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except:
    pass

# ===== تنظیمات =====
DB_FILE = "ahram_v2.db"
INITIAL_CAPITAL = 100_000_000
RISK_PER_TRADE = 0.05
COMMISSION = 0.0015
STOP_LOSS_PCT = 0.12
TAKE_PROFIT_PCT = 0.20
BUY_THRESHOLD = 55
SELL_THRESHOLD = 45
MIN_ALIGNED = 3


# ===== دریافت دیتا از دیتابیس =====
def load_data():
    """بارگذاری دیتا از SQLite"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT time, last_price FROM prices WHERE last_price>0 ORDER BY id")
        data = cur.fetchall()
        conn.close()
        
        records = []
        for row in data:
            try:
                price = float(row[1])
                if price > 0:
                    records.append({"date": row[0], "close": price})
            except:
                continue
        
        print(f"  ✅ {len(records)} رکورد بارگذاری شد")
        return records
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        return []


# ===== اندیکاتورها =====
def calc_ema(prices, period):
    if len(prices) < period:
        return prices[-1]
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_macd(prices):
    if len(prices) < 26:
        return 0, 0
    ema12 = calc_ema(prices, 12)
    ema26 = calc_ema(prices, 26)
    macd = ema12 - ema26
    signal = macd * 0.8
    return macd, signal


def calc_bollinger(prices, period=20):
    if len(prices) < period:
        return prices[-1], prices[-1], prices[-1]
    recent = prices[-period:]
    middle = sum(recent) / period
    std = math.sqrt(sum((p - middle) ** 2 for p in recent) / period)
    return middle + 2 * std, middle, middle - 2 * std


# ===== تحلیل استراتژی =====
def analyze(prices, index):
    if index < 50:
        return "WATCH", 0
    
    p = prices[:index+1]
    current = p[-1]
    scores = {}
    
    # EMA
    ema9 = calc_ema(p, 9)
    ema21 = calc_ema(p, 21)
    ema50 = calc_ema(p, 50)
    if current > ema9 > ema21 > ema50:
        scores["EMA"] = 70
    elif current < ema9 < ema21 < ema50:
        scores["EMA"] = 30
    else:
        scores["EMA"] = 50
    
    # RSI
    rsi = calc_rsi(p)
    if rsi < 30:
        scores["RSI"] = 70
    elif rsi > 70:
        scores["RSI"] = 30
    else:
        scores["RSI"] = 50
    
    # MACD
    macd, signal = calc_macd(p)
    if macd > signal:
        scores["MACD"] = 65
    elif macd < signal:
        scores["MACD"] = 35
    else:
        scores["MACD"] = 50
    
    # بولینگر
    upper, middle, lower = calc_bollinger(p)
    if current < lower:
        scores["Bollinger"] = 70
    elif current > upper:
        scores["Bollinger"] = 30
    else:
        scores["Bollinger"] = 50
    
    # پرایس اکشن
    if len(p) >= 3:
        if p[-1] > p[-2] > p[-3]:
            scores["Price"] = 65
        elif p[-1] < p[-2] < p[-3]:
            scores["Price"] = 35
        else:
            scores["Price"] = 50
    
    # محاسبه امتیاز
    weights = {"EMA": 25, "RSI": 20, "MACD": 20, "Bollinger": 15, "Price": 20}
    total = sum(scores.get(k, 50) * w for k, w in weights.items()) / sum(weights.values())
    
    bullish = sum(1 for v in scores.values() if v > 55)
    bearish = sum(1 for v in scores.values() if v < 45)
    
    if total >= BUY_THRESHOLD and bullish >= MIN_ALIGNED:
        return "BUY", round(total)
    elif total <= SELL_THRESHOLD and bearish >= MIN_ALIGNED:
        return "SELL", round(total)
    return "WATCH", round(total)


# ===== کلاس معامله =====
class Trade:
    def __init__(self, entry_date, entry_price, direction):
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.direction = direction
        self.exit_date = None
        self.exit_price = None
        self.profit_pct = 0
        self.status = "OPEN"
        self.exit_reason = ""
    
    def check_exit(self, price, date):
        if self.status != "OPEN":
            return False
        
        if self.direction == "BUY":
            change = (price - self.entry_price) / self.entry_price
        else:
            change = (self.entry_price - price) / self.entry_price
        
        if change >= TAKE_PROFIT_PCT:
            self.close(price, date, "TAKE PROFIT")
            return True
        elif change <= -STOP_LOSS_PCT:
            self.close(price, date, "STOP LOSS")
            return True
        return False
    
    def close(self, price, date, reason):
        self.exit_price = price
        self.exit_date = date
        self.exit_reason = reason
        self.status = "CLOSED"
        
        if self.direction == "BUY":
            self.profit_pct = (price - self.entry_price) / self.entry_price * 100
        else:
            self.profit_pct = (self.entry_price - price) / self.entry_price * 100
        
        self.profit_pct -= COMMISSION * 200  # کارمزد


# ===== اجرای بک‌تست =====
def run_backtest(records):
    trades = []
    open_trade = None
    signals = []
    
    for i in range(50, len(records)):
        price = records[i]["close"]
        date = records[i]["date"]
        
        # بررسی خروج
        if open_trade and open_trade.status == "OPEN":
            if open_trade.check_exit(price, date):
                trades.append(open_trade)
                open_trade = None
        
        # تحلیل
        action, score = analyze([r["close"] for r in records], i)
        
        # ورود
        if open_trade is None and action in ("BUY", "SELL"):
            open_trade = Trade(date, price, action)
            signals.append({"date": date, "action": action, "price": price, "score": score})
    
    # بستن معامله باز
    if open_trade and open_trade.status == "OPEN":
        open_trade.close(records[-1]["close"], records[-1]["date"], "END")
        trades.append(open_trade)
    
    return trades, signals


# ===== گزارش =====
def print_report(trades, signals):
    print(f"\n{'='*60}")
    print(f"📊 گزارش بک‌تست اهرم")
    print(f"{'='*60}")
    
    if not trades:
        print("  ❌ هیچ معامله‌ای انجام نشد!")
        return
    
    wins = [t for t in trades if t.profit_pct > 0]
    losses = [t for t in trades if t.profit_pct <= 0]
    
    total_profit = sum(t.profit_pct for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    
    capital = INITIAL_CAPITAL
    for t in trades:
        capital += capital * RISK_PER_TRADE * (t.profit_pct / 100)
    
    print(f"\n  📈 آمار:")
    print(f"    کل معاملات:   {len(trades)}")
    print(f"    برد:           {len(wins)} ({win_rate:.1f}%)")
    print(f"    باخت:         {len(losses)} ({100-win_rate:.1f}%)")
    print(f"    سود کل:       {total_profit:.1f}%")
    
    print(f"\n  💰 سرمایه:")
    print(f"    اولیه:         {INITIAL_CAPITAL:,.0f}")
    print(f"    نهایی:         {capital:,.0f}")
    print(f"    بازده:         {((capital-INITIAL_CAPITAL)/INITIAL_CAPITAL*100):.1f}%")
    
    print(f"\n  📋 آخرین معاملات:")
    for t in trades[-10:]:
        emoji = "✅" if t.profit_pct > 0 else "❌"
        print(f"    {emoji} {t.entry_date[:10]} | {t.direction} | {t.entry_price:,.0f} → {t.exit_price:,.0f} | {t.profit_pct:+.1f}% | {t.exit_reason}")
    
    print(f"\n  📊 سیگنال‌ها: {len(signals)}")
    print(f"{'='*60}")


# ===== اصل =====
def main():
    print("╔" + "═" * 58 + "╗")
    print("║" + "  AHRAM AI - BACKTEST  ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    
    records = load_data()
    if len(records) < 100:
        print("❌ دیتای کافی نیست!")
        return
    
    print(f"\n  📊 دیتا: {records[0]['date']} تا {records[-1]['date']}")
    print(f"  📈 قیمت: {records[0]['close']:,.0f} → {records[-1]['close']:,.0f}")
    
    trades, signals = run_backtest(records)
    print_report(trades, signals)


if __name__ == "__main__":
    main()