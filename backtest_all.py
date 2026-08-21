# -*- coding: utf-8 -*-
"""
AHRAM AI - BACKTEST ENGINE (3 نماد)
بک‌تست با دیتای brsapi.ir
"""
import sys
import json
import math
import sqlite3
import requests
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except:
    pass

# ===== تنظیمات =====
API_KEY = "BMDsjrQG9X4S7vqVrrW8eDXGbPHDYBeL"
API_URL = "https://api.brsapi.ir/Tsetmc/History.php"

SYMBOLS = {
    "اهرم": {"db": "ahram_v2.db", "l18": "اهرم"},
    "وبملت": {"db": "webmellt.db", "l18": "وبملت"},
    "شستا": {"db": "shasta.db", "l18": "شستا"},
}

INITIAL_CAPITAL = 100_000_000
RISK_PER_TRADE = 0.05
COMMISSION = 0.0015
STOP_LOSS_PCT = 0.12
TAKE_PROFIT_PCT = 0.20
BUY_THRESHOLD = 55
SELL_THRESHOLD = 45
MIN_ALIGNED = 3


# ===== دریافت دیتا =====
def fetch_history(symbol_l18):
    try:
        url = f"{API_URL}?key={API_KEY}&type=0&l18={symbol_l18}"
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        
        records = []
        for item in data:
            try:
                price = float(item.get("pl", 0))
                vol = float(item.get("tvol", 0))
                if price > 0 and vol > 0:
                    records.append({
                        "date": item.get("date", ""),
                        "open": float(item.get("pf", 0)),
                        "high": float(item.get("pmax", 0)),
                        "low": float(item.get("pmin", 0)),
                        "close": price,
                        "volume": vol,
                    })
            except:
                continue
        
        records.reverse()
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
        
        self.profit_pct -= COMMISSION * 200


# ===== اجرای بک‌تست =====
def run_backtest(records):
    trades = []
    open_trade = None
    
    for i in range(50, len(records)):
        price = records[i]["close"]
        date = records[i]["date"]
        
        if open_trade and open_trade.status == "OPEN":
            if open_trade.check_exit(price, date):
                trades.append(open_trade)
                open_trade = None
        
        action, score = analyze([r["close"] for r in records], i)
        
        if open_trade is None and action in ("BUY", "SELL"):
            open_trade = Trade(date, price, action)
    
    if open_trade and open_trade.status == "OPEN":
        open_trade.close(records[-1]["close"], records[-1]["date"], "END")
        trades.append(open_trade)
    
    return trades


# ===== گزارش =====
def print_report(symbol, trades):
    print(f"\n{'='*60}")
    print(f"📊 {symbol}")
    print(f"{'='*60}")
    
    if not trades:
        print("  ❌ هیچ معامله‌ای انجام نشد!")
        return {"trades": 0, "wins": 0, "profit": 0, "return_pct": 0}
    
    wins = [t for t in trades if t.profit_pct > 0]
    losses = [t for t in trades if t.profit_pct <= 0]
    
    total_profit = sum(t.profit_pct for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    
    capital = INITIAL_CAPITAL
    for t in trades:
        capital += capital * RISK_PER_TRADE * (t.profit_pct / 100)
    
    return_pct = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    
    print(f"  معاملات: {len(trades)} | برد: {len(wins)} ({win_rate:.0f}%) | باخت: {len(losses)}")
    print(f"  سود معاملات: {total_profit:.1f}%")
    print(f"  سرمایه: {INITIAL_CAPITAL:,.0f} → {capital:,.0f}")
    print(f"  بازده: {return_pct:.1f}%")
    
    print(f"\n  آخرین ۵ معامله:")
    for t in trades[-5:]:
        emoji = "✅" if t.profit_pct > 0 else "❌"
        print(f"    {emoji} {t.entry_date[:10]} | {t.direction} | {t.profit_pct:+.1f}% | {t.exit_reason}")
    
    return {"trades": len(trades), "wins": len(wins), "profit": total_profit, "return_pct": return_pct}


# ===== ذخیره در دیتابیس =====
def save_to_db(symbol, db_name, records):
    """توجه: این تابع مستقیم توی همون دیتابیسی می‌نویسه که ربات زنده استفاده
    می‌کنه (ahram_v2.db و غیره). قبل از درج، تاریخ‌های موجود رو چک می‌کنیم
    که اگه این اسکریپت چندبار اجرا بشه، تاریخچه‌ی قیمت تکراری نشه."""
    try:
        conn = sqlite3.connect(db_name)
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS prices(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT, last_price REAL, closing_price REAL, volume REAL, trades INTEGER)""")

        cur.execute("SELECT DISTINCT substr(time,1,10) FROM prices")
        existing_dates = {row[0] for row in cur.fetchall() if row[0]}

        inserted, skipped = 0, 0
        for r in records:
            date_key = str(r["date"])[:10]
            if date_key in existing_dates:
                skipped += 1
                continue
            cur.execute("INSERT INTO prices(time, last_price, closing_price, volume, trades) VALUES(?,?,?,?,?)",
                (r["date"], r["close"], r["close"], r["volume"], 0))
            existing_dates.add(date_key)
            inserted += 1

        conn.commit()
        conn.close()
        print(f"  ✅ {inserted} رکورد جدید در {db_name} ذخیره شد ({skipped} رکورد تکراری رد شد)")
    except Exception as e:
        print(f"  ❌ خطا ذخیره: {e}")


# ===== اصل =====
def main():
    print("╔" + "═" * 58 + "╗")
    print("║" + "  AHRAM AI - BACKTEST (3 نماد)  ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    
    print(f"\n⚙️ تنظیمات:")
    print(f"  سرمایه: {INITIAL_CAPITAL:,.0f}")
    print(f"  ریسک: {RISK_PER_TRADE*100}%")
    print(f"  حد ضرر: {STOP_LOSS_PCT*100}% | حد سود: {TAKE_PROFIT_PCT*100}%")
    
    results = {}
    
    for symbol, info in SYMBOLS.items():
        print(f"\n{'#'*60}")
        print(f"# {symbol}")
        print(f"{'#'*60}")
        
        # دریافت دیتا
        print(f"  📥 دریافت دیتا از brsapi...")
        records = fetch_history(info["l18"])
        
        if len(records) < 60:
            print(f"  ⚠️ دیتای کافی نیست ({len(records)} رکورد)")
            continue
        
        print(f"  ✅ {len(records)} رکورد از {records[0]['date']} تا {records[-1]['date']}")
        
        # ذخیره در دیتابیس
        save_to_db(symbol, info["db"], records)
        
        # بک‌تست
        trades = run_backtest(records)
        result = print_report(symbol, trades)
        results[symbol] = result
    
    # خلاصه کلی
    if results:
        print(f"\n{'='*60}")
        print(f"📊 خلاصه کلی")
        print(f"{'='*60}")
        
        total_trades = sum(r["trades"] for r in results.values())
        total_wins = sum(r["wins"] for r in results.values())
        
        print(f"\n  کل معاملات: {total_trades}")
        print(f"  کل بردها: {total_wins}")
        if total_trades > 0:
            print(f"  نرخ برد: {total_wins/total_trades*100:.0f}%")
        
        print(f"\n  نتایج هر نماد:")
        for symbol, result in results.items():
            print(f"    {symbol}: {result['trades']} معامله | {result['return_pct']:.1f}% بازده")
        
        avg_return = sum(r["return_pct"] for r in results.values()) / len(results)
        print(f"\n  میانگین بازده: {avg_return:.1f}%")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()