# -*- coding: utf-8 -*-
"""
AHRAM STRATEGY - نسخه نهایی اصلاح‌شده
۹ اندیکاتور + EMA/MACD/ADX + Fibonacci + RSI Divergence
"""
import sqlite3
from datetime import datetime, time as dtime

import pandas as pd

import config

from ichimoku import Ichimoku
from vwap import VWAP
from price_action import PriceAction
from market_regime import MarketRegime
from heikin_ashi import calculate_heikin_ashi
import heikin_ashi as _ha_module
from multi_timeframe import calculate_multi_timeframe
from bollinger import Bollinger
from rsi import RSI
from fibonacci import Fibonacci
from rsi_divergence import RSIDivergence
from ema import EMA
from macd import MACD
from adx import ADX


class Strategy:

    BUY_THRESHOLD = getattr(config, "BUY_THRESHOLD", 45)
    SELL_THRESHOLD = getattr(config, "SELL_THRESHOLD", -45)
    MIN_ALIGNED_INDICATORS = getattr(config, "MIN_ALIGNED_INDICATORS", 4)

    TOTAL_INDICATORS = 12

    QUIET_START_MINUTES = 3
    QUIET_END_MINUTES = 3

    MARKET_OPEN = dtime(9, 0)
    MARKET_CLOSE = dtime(12, 30)

    RSI_OVERSOLD = 20
    RSI_OVERBOUGHT = 85

    STALE_PRICE_TICKS = 6
    ALIGNED_CONV = 0.2
    QUEUE_GAP_MIN = 1.5

    def __init__(self):
        self.conn = sqlite3.connect(config.DATABASE_NAME)
        self.df = None
        self.ich = None
        self.vwap = None
        self.pa = None
        self.boll = None
        self.fib = None
        self.rsi_div = None
        self.ema_obj = None
        self.macd_obj = None
        self.adx_obj = None
        self.ha_strength = 50.0
        self.queue_type = None
        self.queue_gap = 0.0

    def close(self):
        if self.conn:
            self.conn.close()

    def load_data(self):
        query = """
            SELECT time, last_price, closing_price, volume
            FROM prices
            ORDER BY id
        """
        df = pd.read_sql(query, self.conn)
        if df.empty:
            return None
        if len(df) < 20:
            print("NOT ENOUGH DATA")
            return None
        df["price"] = df["last_price"]
        df["HIGH20"] = df["last_price"].rolling(20).max()
        df["LOW20"] = df["last_price"].rolling(20).min()
        return df

    def _in_quiet_period(self):
        now = datetime.now().time()
        open_minutes = self.MARKET_OPEN.hour * 60 + self.MARKET_OPEN.minute
        close_minutes = self.MARKET_CLOSE.hour * 60 + self.MARKET_CLOSE.minute
        now_minutes = now.hour * 60 + now.minute
        if now_minutes < open_minutes + self.QUIET_START_MINUTES:
            return True
        if now_minutes > close_minutes - self.QUIET_END_MINUTES:
            return True
        return False

    def _detect_queue(self, locked_price):
        try:
            df = self.df
            if "time" not in df.columns or len(df) < 10:
                return None, 0.0
            times = df["time"].astype(str)
            today = str(times.iloc[-1])[:10]
            prev = df[times.str[:10] != today]["last_price"]
            if len(prev) < 3:
                return None, 0.0
            yclose = float(prev.iloc[-1])
            if yclose <= 0:
                return None, 0.0
            gap = (locked_price - yclose) / yclose * 100.0
            if gap >= self.QUEUE_GAP_MIN:
                return "BUY", round(gap, 2)
            if gap <= -self.QUEUE_GAP_MIN:
                return "SELL", round(gap, 2)
            return None, round(gap, 2)
        except Exception:
            return None, 0.0

    @staticmethod
    def _conviction(strength):
        try:
            if strength is None or pd.isna(strength):
                return 0.0
            s = float(strength)
            if s != s:
                return 0.0
            return max(-1.0, min(1.0, (s - 50.0) / 50.0))
        except Exception:
            return 0.0

    @staticmethod
    def _regime_conviction(regime):
        if not isinstance(regime, dict):
            return 0.0
        mag_map = {"STRONG": 1.0, "MEDIUM": 0.6, "WEAK": 0.3}
        mag = mag_map.get(str(regime.get("strength", "")).upper(), 0.5)
        trend = regime.get("trend")
        if trend == "BULL":
            return mag
        if trend == "BEAR":
            return -mag
        return 0.0

    def _calculate_score(self, mtf_signal, regime):
        ich_c = self._conviction(self.ich.strength)
        vwap_c = self._conviction(self.vwap.strength)
        pa_c = self._conviction(self.pa.strength)
        ha_c = self._conviction(self.ha_strength)
        boll_c = self._conviction(self.boll.strength)
        regime_c = self._regime_conviction(regime)
        mtf_c = 1.0 if mtf_signal == "BULLISH" else (-1.0 if mtf_signal == "BEARISH" else 0.0)
        fib_c = self._conviction(self.fib.strength) if self.fib else 0.0
        rsi_div_c = self._conviction(self.rsi_div.strength) if self.rsi_div else 0.0
        ema_c = self._conviction(self.ema_obj.strength) if self.ema_obj else 0.0
        macd_c = self._conviction(self.macd_obj.strength) if self.macd_obj else 0.0
        adx_c = self._conviction(self.adx_obj.strength) if self.adx_obj else 0.0

        parts = [
            ("Ichimoku", ich_c, 12),
            ("VWAP", vwap_c, 6),
            ("Price Action", pa_c, 10),
            ("Market Regime", regime_c, 10),
            ("Heikin Ashi", ha_c, 10),
            ("Multi-Timeframe", mtf_c, 10),
            ("Bollinger", boll_c, 6),
            ("Fibonacci", fib_c, 9),
            ("RSI Divergence", rsi_div_c, 8),
            ("EMA", ema_c, 7),
            ("MACD", macd_c, 6),
            ("ADX", adx_c, 6),
        ]

        score = sum(conv * weight for _, conv, weight in parts)
        bullish_count = sum(1 for _, c, _ in parts if c > self.ALIGNED_CONV)
        bearish_count = sum(1 for _, c, _ in parts if c < -self.ALIGNED_CONV)
        aligned_count = max(bullish_count, bearish_count)

        reasons = [
            f"{name} {'Bullish' if c > 0 else 'Bearish'}"
            for name, c, _ in parts
            if abs(c) > self.ALIGNED_CONV
        ]
        return score, reasons, aligned_count, bullish_count, bearish_count, parts

    def analyze(self):
        self.df = self.load_data()
        if self.df is None:
            return None

        self.ich = Ichimoku(self.df)
        ichimoku_signal = self.ich.calculate()

        self.vwap = VWAP(self.df)
        vwap_signal = self.vwap.calculate()

        self.pa = PriceAction(self.df)
        price_action = self.pa.analyze()

        regime = MarketRegime(self.df).analyze()

        heikin_signal = calculate_heikin_ashi()
        self.ha_strength = (
            _ha_module.LAST_RESULT.get("strength", 50.0)
            if isinstance(_ha_module.LAST_RESULT, dict) else 50.0
        )

        mtf_signal = calculate_multi_timeframe()

        self.boll = Bollinger(self.df)
        bollinger_signal = self.boll.calculate()

        rsi_value = RSI(self.df).calculate()

        self.fib = Fibonacci(self.df)
        fib_signal = self.fib.calculate()

        self.rsi_div = RSIDivergence(self.df)
        rsi_div_signal = self.rsi_div.calculate()

        self.ema_obj = EMA(self.df)
        ema_signal = self.ema_obj.calculate()

        self.macd_obj = MACD(self.df)
        macd_signal = self.macd_obj.calculate()

        self.adx_obj = ADX(self.df)
        adx_signal = self.adx_obj.calculate()

        recent_prices = self.df["last_price"].tail(self.STALE_PRICE_TICKS)
        flat = len(recent_prices) >= self.STALE_PRICE_TICKS and recent_prices.nunique() == 1
        stale_price = False
        self.queue_type = None
        self.queue_gap = 0.0
        if flat:
            locked = float(recent_prices.iloc[-1])
            self.queue_type, self.queue_gap = self._detect_queue(locked)
            if self.queue_type is None:
                stale_price = True

        (score, reasons, aligned_count, bullish_count,
         bearish_count, parts) = self._calculate_score(mtf_signal, regime)

        lookback = getattr(config, "MOMENTUM_LOOKBACK", 5)
        if len(self.df) >= lookback:
            recent = self.df["last_price"].tail(lookback)
            if float(recent.iloc[0]) > 0:
                move_pct = (float(recent.iloc[-1]) - float(recent.iloc[0])) / float(recent.iloc[0]) * 100
                m_th = getattr(config, "MOMENTUM_THRESHOLD", 0.4)
                if abs(move_pct) > m_th:
                    score += (1 if move_pct > 0 else -1) * getattr(config, "MOMENTUM_BONUS", 12)
                    reasons.append(f"Momentum Surge ({'+' if move_pct > 0 else ''}{move_pct:.1f}%)")

        if self.queue_type == "BUY":
            reasons.append(f"🔥 صف خرید (+{self.queue_gap}% روی سقف)")
        elif self.queue_type == "SELL":
            reasons.append(f"🔻 صف فروش ({self.queue_gap}% روی کف)")

        if self.fib and self.fib.current_zone != "MIDDLE":
            reasons.append(f"Fibonacci: {self.fib.current_zone}")
        if self.rsi_div and self.rsi_div.divergence_type:
            reasons.append(f"RSI Divergence: {self.rsi_div.divergence_type}")

        confidence = round((aligned_count / self.TOTAL_INDICATORS) * 100)
        enough_agreement = aligned_count >= self.MIN_ALIGNED_INDICATORS
        quiet_period = self._in_quiet_period()

        rsi_veto = False
        if rsi_value is not None and self.queue_type is None:
            if score <= self.SELL_THRESHOLD and rsi_value <= self.RSI_OVERSOLD:
                rsi_veto = True
            elif score >= self.BUY_THRESHOLD and rsi_value >= self.RSI_OVERBOUGHT:
                rsi_veto = True
        if self.queue_type is not None and rsi_value is not None:
            print(f"RSI VETO BYPASS: صف {self.queue_type} تشخیص -> RSI خنثی نشد")

        if stale_price and self.queue_type is None:
            action = "WATCH"
            print("STALE PRICE: قیمت راکد -> WATCH اجباری")
        elif quiet_period:
            action = "WATCH"
            print("QUIET PERIOD: نزدیک باز/بسته شدن بازار")
        elif rsi_veto:
            action = "WATCH"
            print(f"RSI VETO: RSI={rsi_value} (آستانه: {self.RSI_OVERBOUGHT}) -> خنثی شد")
        elif score >= self.BUY_THRESHOLD and enough_agreement and bullish_count >= bearish_count:
            action = "BUY"
        elif score <= self.SELL_THRESHOLD and enough_agreement and bearish_count >= bullish_count:
            action = "SELL"
        else:
            action = "WATCH"

        price = float(self.df.iloc[-1]["last_price"])

        if self.queue_type == "BUY":
            print(f"🔥 صف خرید: قیمت +{self.queue_gap}% روی سقف قفل شده")
        elif self.queue_type == "SELL":
            print(f"🔻 صف فروش: قیمت {self.queue_gap}% روی کف قفل شده")

        if self.fib:
            print(f"[FIB] zone={self.fib.current_zone} | support={self.fib.nearest_support} | resistance={self.fib.nearest_resistance}")
        if self.rsi_div:
            print(f"[RSI-DIV] {self.rsi_div.divergence_type or 'NONE'} | RSI={self.rsi_div.details.get('current_rsi')}")
        if self.ema_obj:
            print(f"[EMA] {ema_signal} | strength={self.ema_obj.strength}")
        if self.macd_obj:
            print(f"[MACD] {macd_signal} | strength={self.macd_obj.strength}")
        if self.adx_obj:
            print(f"[ADX] {adx_signal} | strength={self.adx_obj.strength}")

        return (action, confidence, round(score, 1), price)


if __name__ == "__main__":
    strategy = Strategy()
    try:
        strategy.analyze()
    finally:
        strategy.close()