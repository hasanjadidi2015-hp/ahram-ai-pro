# -*- coding: utf-8 -*-
"""
AHRAM AI - BACKTEST v4 (کامل)
اندیکاتورها + Price Action + Heikin Ashi + اخبار
"""
import sys
import sqlite3
import math

try:
    sys.stdout.reconfigure(encoding="utf-8")
except:
    pass

DB_FILE = "ahram_v2.db"
INITIAL_CAPITAL = 100_000_000
RISK_PER_TRADE = 0.05
COMMISSION = 0.0015
STOP_LOSS_PCT = 0.12
TAKE_PROFIT_PCT = 0.20


def load_data():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT time, last_price FROM prices WHERE last_price>0 ORDER BY id")
    data = cur.fetchall()
    conn.close()
    return [{"date": r[0], "close": float(r[1])} for r in data if r[1] and float(r[1]) > 0]


# ===== اندیکاتورهای پایه =====

def calc_ema(prices, period):
    if len(prices) < period:
        return prices[-1]
    m = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p - ema) * m + ema
    return ema


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    d = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    g = [x if x > 0 else 0 for x in d[-period:]]
    l = [-x if x < 0 else 0 for x in d[-period:]]
    ag = sum(g) / period
    al = sum(l) / period
    if al == 0:
        return 100
    return 100 - (100 / (1 + ag / al))


def calc_macd(prices):
    if len(prices) < 26:
        return 0, 0
    e12 = calc_ema(prices, 12)
    e26 = calc_ema(prices, 26)
    return e12 - e26, (e12 - e26) * 0.85


def calc_bollinger(prices, period=20):
    if len(prices) < period:
        return prices[-1], prices[-1], prices[-1]
    r = prices[-period:]
    m = sum(r) / period
    s = math.sqrt(sum((p - m) ** 2 for p in r) / period)
    return m + 2 * s, m, m - 2 * s


def calc_ichimoku(prices):
    if len(prices) < 52:
        return "NEUTRAL"
    tenkan = (max(prices[-9:]) + min(prices[-9:])) / 2
    kijun = (max(prices[-26:]) + min(prices[-26:])) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (max(prices[-52:]) + min(prices[-52:])) / 2
    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)
    current = prices[-1]
    if current > cloud_top and tenkan > kijun:
        return "BUY"
    elif current < cloud_bottom and tenkan < kijun:
        return "SELL"
    return "NEUTRAL"


def calc_fibonacci(prices):
    if len(prices) < 50:
        return "NEUTRAL"
    recent = prices[-50:]
    high = max(recent)
    low = min(recent)
    current = prices[-1]
    if high == low:
        return "NEUTRAL"
    position = (current - low) / (high - low)
    if position < 0.382:
        return "BUY"
    elif position > 0.618:
        return "SELL"
    return "NEUTRAL"


def calc_stochastic(prices, period=14):
    if len(prices) < period:
        return "NEUTRAL"
    recent = prices[-period:]
    low = min(recent)
    high = max(recent)
    if high == low:
        return "NEUTRAL"
    k = (prices[-1] - low) / (high - low) * 100
    if k < 20:
        return "BUY"
    elif k > 80:
        return "SELL"
    return "NEUTRAL"


def calc_cci(prices, period=20):
    if len(prices) < period:
        return "NEUTRAL"
    recent = prices[-period:]
    mean = sum(recent) / period
    mean_dev = sum(abs(p - mean) for p in recent) / period
    if mean_dev == 0:
        return "NEUTRAL"
    cci = (prices[-1] - mean) / (0.015 * mean_dev)
    if cci < -100:
        return "BUY"
    elif cci > 100:
        return "SELL"
    return "NEUTRAL"


def calc_williams_r(prices, period=14):
    if len(prices) < period:
        return "NEUTRAL"
    recent = prices[-period:]
    low = min(recent)
    high = max(recent)
    if high == low:
        return "NEUTRAL"
    wr = (high - prices[-1]) / (high - low) * -100
    if wr < -80:
        return "BUY"
    elif wr > -20:
        return "SELL"
    return "NEUTRAL"


def calc_adx(prices, period=14):
    if len(prices) < period * 2:
        return "NEUTRAL"
    changes = [prices[i] - prices[i-1] for i in range(len(prices)-period, len(prices))]
    plus = sum(max(0, c) for c in changes)
    minus = sum(max(0, -c) for c in changes)
    total = plus + minus
    if total == 0:
        return "NEUTRAL"
    if plus / total > 0.6:
        return "BUY"
    elif minus / total > 0.6:
        return "SELL"
    return "NEUTRAL"


def calc_momentum(prices, period=10):
    if len(prices) < period + 1:
        return "NEUTRAL"
    mom = (prices[-1] - prices[-period]) / prices[-period] * 100
    if mom > 5:
        return "BUY"
    elif mom < -5:
        return "SELL"
    return "NEUTRAL"


def calc_vwap(prices):
    if len(prices) < 20:
        return "NEUTRAL"
    vwap = sum(prices[-20:]) / 20
    if prices[-1] > vwap * 1.02:
        return "BUY"
    elif prices[-1] < vwap * 0.98:
        return "SELL"
    return "NEUTRAL"


# ===== Heikin Ashi =====

def calc_heikin_ashi(prices):
    """محاسبه Heikin Ashi و تشخیص روند"""
    if len(prices) < 5:
        return "NEUTRAL"
    
    # محاسبه Heikin Ashi
    ha_close = (prices[-1] + prices[-2] + prices[-3] + prices[-4]) / 4
    ha_open = (prices[-2] + prices[-3]) / 2
    
    # تشخیص روند
    if ha_close > ha_open:
        # کندل سبز
        if prices[-1] > prices[-2] > prices[-3]:
            return "BUY"  # روند صعودی قوی
        return "BUY"
    elif ha_close < ha_open:
        # کندل قرمز
        if prices[-1] < prices[-2] < prices[-3]:
            return "SELL"  # روند نزولی قوی
        return "SELL"
    return "NEUTRAL"


# ===== Price Action پیشرفته =====

def calc_price_action(prices):
    """تشخیص الگوهای کندلی"""
    if len(prices) < 5:
        return "NEUTRAL"
    
    signals = []
    
    # الگوی Engulfing صعودی
    if prices[-2] < prices[-3] and prices[-1] > prices[-2] and prices[-1] > prices[-3]:
        signals.append("BUY")
    
    # الگوی Engulfing نزولی
    if prices[-2] > prices[-3] and prices[-1] < prices[-2] and prices[-1] < prices[-3]:
        signals.append("SELL")
    
    # الگوی Hammer (چکش)
    if prices[-1] > prices[-2] and (prices[-2] - min(prices[-3], prices[-1])) > 2 * abs(prices[-1] - prices[-2]):
        signals.append("BUY")
    
    # الگوی Shooting Star (ستاره دنباله‌دار)
    if prices[-1] < prices[-2] and (max(prices[-3], prices[-1]) - prices[-2]) > 2 * abs(prices[-1] - prices[-2]):
        signals.append("SELL")
    
    # الگوی Doji (دوجی) - بی‌تصمیمی
    if abs(prices[-1] - prices[-2]) < (max(prices[-1], prices[-2]) - min(prices[-1], prices[-2])) * 0.1:
        return "NEUTRAL"
    
    # الگوی Three White Soldiers (سه سرباز سفید)
    if prices[-1] > prices[-2] > prices[-3] > prices[-4]:
        signals.append("BUY")
    
    # الگوی Three Black Crows (سه کلاغ سیاه)
    if prices[-1] < prices[-2] < prices[-3] < prices[-4]:
        signals.append("SELL")
    
    # الگوی Morning Star (ستاره صبحگاهی)
    if prices[-3] > prices[-2] and prices[-1] > prices[-2] and prices[-1] > (prices[-3] + prices[-2]) / 2:
        signals.append("BUY")
    
    # الگوی Evening Star (ستاره شامگاهی)
    if prices[-3] < prices[-2] and prices[-1] < prices[-2] and prices[-1] < (prices[-3] + prices[-2]) / 2:
        signals.append("SELL")
    
    # تصمیم‌گیری نهایی
    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL")
    
    if buy_count > sell_count:
        return "BUY"
    elif sell_count > buy_count:
        return "SELL"
    return "NEUTRAL"


# ===== تحلیل اخبار ( sentiment بازار) =====

def calc_news_sentiment(prices, volumes=None):
    """تحلیل sentiment بازار بر اساس رفتار قیمت"""
    if len(prices) < 20:
        return "NEUTRAL"
    
    # محاسبه تغییرات اخیر
    recent_change = (prices[-1] - prices[-5]) / prices[-5] * 100
    weekly_change = (prices[-1] - prices[-20]) / prices[-20] * 100
    
    # نوسانات اخیر
    volatility = sum(abs(prices[i] - prices[i-1]) for i in range(-5, 0)) / 5
    
    # sentiment بر اساس رفتار قیمت
    if recent_change > 3 and weekly_change > 5:
        return "BUY"  # بازار مثبت
    elif recent_change < -3 and weekly_change < -5:
        return "SELL"  # بازار منفی
    elif volatility > prices[-1] * 0.03:
        return "NEUTRAL"  # نوسان زیاد = بی‌تصمیم
    return "NEUTRAL"


# ===== تحلیل جامع =====

def get_all_signals(prices, idx):
    if idx < 52:
        return {}
    p = prices[:idx+1]
    current = p[-1]
    signals = {}
    
    # اندیکاتورهای پایه
    ema9 = calc_ema(p, 9)
    ema21 = calc_ema(p, 21)
    ema50 = calc_ema(p, 50)
    if current > ema9 > ema21 > ema50:
        signals["EMA"] = "BUY"
    elif current < ema9 < ema21 < ema50:
        signals["EMA"] = "SELL"
    else:
        signals["EMA"] = "NEUTRAL"
    
    rsi = calc_rsi(p)
    if rsi < 30:
        signals["RSI"] = "BUY"
    elif rsi > 70:
        signals["RSI"] = "SELL"
    else:
        signals["RSI"] = "NEUTRAL"
    
    macd, signal = calc_macd(p)
    if macd > signal:
        signals["MACD"] = "BUY"
    elif macd < signal:
        signals["MACD"] = "SELL"
    else:
        signals["MACD"] = "NEUTRAL"
    
    upper, middle, lower = calc_bollinger(p)
    if current < lower:
        signals["Bollinger"] = "BUY"
    elif current > upper:
        signals["Bollinger"] = "SELL"
    else:
        signals["Bollinger"] = "NEUTRAL"
    
    signals["Ichimoku"] = calc_ichimoku(p)
    signals["Fibonacci"] = calc_fibonacci(p)
    signals["VWAP"] = calc_vwap(p)
    signals["Stochastic"] = calc_stochastic(p)
    signals["CCI"] = calc_cci(p)
    signals["Williams_R"] = calc_williams_r(p)
    signals["ADX"] = calc_adx(p)
    signals["Momentum"] = calc_momentum(p)
    
    # اندیکاتورهای جدید
    signals["Heikin_Ashi"] = calc_heikin_ashi(p)
    signals["Price_Action"] = calc_price_action(p)
    signals["News_Sentiment"] = calc_news_sentiment(p)
    
    return signals


def get_combined_signal(signals):
    if not signals:
        return "WATCH", 0
    
    weights = {
        "Ichimoku": 3, "RSI": 2.5, "MACD": 2.5, "Fibonacci": 2,
        "EMA": 2, "Bollinger": 1.5, "VWAP": 1.5, "ADX": 1.5,
        "Heikin_Ashi": 2.5, "Price_Action": 2, "News_Sentiment": 1.5,
        "Stochastic": 1, "CCI": 1, "Williams_R": 1, "Momentum": 1,
    }
    
    buy_score = 0
    sell_score = 0
    total_weight = 0
    
    for ind, sig in signals.items():
        w = weights.get(ind, 1)
        total_weight += w
        if sig == "BUY":
            buy_score += w
        elif sig == "SELL":
            sell_score += w
    
    if total_weight == 0:
        return "WATCH", 0
    
    buy_pct = buy_score / total_weight * 100
    sell_pct = sell_score / total_weight * 100
    
    if buy_pct >= 45:
        return "BUY", round(buy_pct)
    elif sell_pct >= 45:
        return "SELL", round(sell_pct)
    return "WATCH", max(round(buy_pct), round(sell_pct))


class Trade:
    def __init__(self, date, price, direction, signals):
        self.entry_date = date
        self.entry_price = price
        self.direction = direction
        self.signals = signals
        self.exit_date = None
        self.exit_price = None
        self.profit_pct = 0
        self.status = "OPEN"
        self.exit_reason = ""
    
    def check_exit(self, price, date):
        if self.status != "OPEN":
            return False
        chg = (price - self.entry_price) / self.entry_price if self.direction == "BUY" else (self.entry_price - price) / self.entry_price
        if chg >= TAKE_PROFIT_PCT:
            self.close(price, date, "TAKE PROFIT")
            return True
        elif chg <= -STOP_LOSS_PCT:
            self.close(price, date, "STOP LOSS")
            return True
        return False
    
    def close(self, price, date, reason):
        self.exit_price, self.exit_date, self.exit_reason = price, date, reason
        self.status = "CLOSED"
        self.profit_pct = ((price - self.entry_price) / self.entry_price * 100) if self.direction == "BUY" else ((self.entry_price - price) / self.entry_price * 100)
        self.profit_pct -= COMMISSION * 200


def run_backtest(records):
    trades = []
    ot = None
    indicator_stats = {}
    prices = [r["close"] for r in records]
    
    for i in range(52, len(records)):
        price = records[i]["close"]
        date = records[i]["date"]
        
        if ot and ot.status == "OPEN" and ot.check_exit(price, date):
            trades.append(ot)
            ot = None
        
        signals = get_all_signals(prices, i)
        action, _ = get_combined_signal(signals)
        
        for ind, sig in signals.items():
            if ind not in indicator_stats:
                indicator_stats[ind] = {"BUY": {"wins": 0, "losses": 0}, "SELL": {"wins": 0, "losses": 0}, "NEUTRAL": 0}
            if sig == "NEUTRAL":
                indicator_stats[ind]["NEUTRAL"] += 1
        
        if ot is None and action in ("BUY", "SELL"):
            ot = Trade(date, price, action, signals)
    
    if ot and ot.status == "OPEN":
        ot.close(records[-1]["close"], records[-1]["date"], "END")
        trades.append(ot)
    
    for trade in trades:
        for ind, sig in trade.signals.items():
            if sig in ("BUY", "SELL"):
                if trade.profit_pct > 0:
                    indicator_stats[ind][sig]["wins"] += 1
                else:
                    indicator_stats[ind][sig]["losses"] += 1
    
    return trades, indicator_stats


def print_report(trades, indicator_stats):
    print(f"\n{'='*60}")
    print(f"📊 گزارش بک‌تست اهرم (کامل)")
    print(f"{'='*60}")
    
    if not trades:
        print("  ❌ معامله‌ای نداشتیم!")
        return
    
    wins = [t for t in trades if t.profit_pct > 0]
    losses = [t for t in trades if t.profit_pct <= 0]
    
    cap = INITIAL_CAPITAL
    for t in trades:
        cap += cap * RISK_PER_TRADE * (t.profit_pct / 100)
    ret = (cap - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    
    print(f"\n  📈 آمار کلی:")
    print(f"    کل معاملات: {len(trades)}")
    print(f"    برد: {len(wins)} ({len(wins)/len(trades)*100:.0f}%)")
    print(f"    باخت: {len(losses)} ({len(losses)/len(trades)*100:.0f}%)")
    print(f"    سود کل: {sum(t.profit_pct for t in trades):.1f}%")
    print(f"    سرمایه: {INITIAL_CAPITAL:,.0f} → {cap:,.0f}")
    print(f"    بازده: {ret:.1f}%")
    
    print(f"\n{'='*60}")
    print(f"📊 عملکرد اندیکاتورها")
    print(f"{'='*60}")
    
    print(f"\n  {'اندیکاتور':<15} {'BUY':<12} {'SELL':<12} {'دقت BUY':<10} {'دقت SELL':<10}")
    print(f"  {'-'*59}")
    
    all_indicators = ["Ichimoku", "RSI", "MACD", "Fibonacci", "EMA", "Bollinger", "VWAP", "ADX", 
                      "Heikin_Ashi", "Price_Action", "News_Sentiment",
                      "Stochastic", "CCI", "Williams_R", "Momentum"]
    
    for ind in all_indicators:
        if ind not in indicator_stats:
            continue
        stats = indicator_stats[ind]
        bt = stats["BUY"]["wins"] + stats["BUY"]["losses"]
        st = stats["SELL"]["wins"] + stats["SELL"]["losses"]
        bw = stats["BUY"]["wins"]
        sw = stats["SELL"]["wins"]
        ba = (bw / bt * 100) if bt > 0 else 0
        sa = (sw / st * 100) if st > 0 else 0
        buy_str = f"{bw}/{bt}" if bt > 0 else "-"
        sell_str = f"{sw}/{st}" if st > 0 else "-"
        buy_acc = f"{ba:.0f}%" if bt > 0 else "-"
        sell_acc = f"{sa:.0f}%" if st > 0 else "-"
        print(f"  {ind:<15} {buy_str:<12} {sell_str:<12} {buy_acc:<10} {sell_acc:<10}")
    
    print(f"\n{'='*60}")
    print(f"🏆 بهترین اندیکاتورها")
    print(f"{'='*60}")
    
    best = []
    for ind, stats in indicator_stats.items():
        bt = stats["BUY"]["wins"] + stats["BUY"]["losses"]
        st = stats["SELL"]["wins"] + stats["SELL"]["losses"]
        total = bt + st
        if total >= 5:
            bw = stats["BUY"]["wins"]
            sw = stats["SELL"]["wins"]
            ba = (bw / bt * 100) if bt > 0 else 0
            sa = (sw / st * 100) if st > 0 else 0
            avg = (ba * bt + sa * st) / total if total > 0 else 0
            best.append((ind, avg, total, ba, sa))
    
    best.sort(key=lambda x: x[1], reverse=True)
    
    for i, (ind, avg, total, ba, sa) in enumerate(best[:5], 1):
        e = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else "  "))
        print(f"  {e} {ind:<15} دقت: {avg:.0f}% | BUY: {ba:.0f}% | SELL: {sa:.0f}% ({total} سیگنال)")
    
    print(f"\n{'='*60}")
    print(f"📋 آخرین 10 معامله")
    print(f"{'='*60}")
    for t in trades[-10:]:
        e = "✅" if t.profit_pct > 0 else "❌"
        print(f"  {e} {t.entry_date[:10]} | {t.direction} | {t.profit_pct:+.1f}% | {t.exit_reason}")


def main():
    print("╔" + "═" * 60 + "╗")
    print("║" + "  AHRAM AI - BACKTEST v4 (کامل)  ".center(60) + "║")
    print("╚" + "═" * 60 + "╝")
    
    records = load_data()
    print(f"\n  📥 دیتا: {len(records)} رکورد")
    print(f"  📅 از {records[0]['date']} تا {records[-1]['date']}")
    print(f"  💰 قیمت: {records[0]['close']:,.0f} → {records[-1]['close']:,.0f}")
    
    trades, indicator_stats = run_backtest(records)
    print_report(trades, indicator_stats)


if __name__ == "__main__":
    main()
