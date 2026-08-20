# -*- coding: utf-8 -*-
"""
OPTION SELECTOR V6 - اصلاح‌شده
    ✅ فیلتر Deep ITM
    ✅ امتیازدهی هوشمند (ATM + Risk/Reward + IV)
    ✅ جریمه IV Crush
"""
import sqlite3

import config

from option_engine import OptionEngine, compute_historical_volatility
from option_decision import OptionDecision
from option_order_book import get_option_bid_ask


# حداقل حجم معاملات روزانه برای نقدشوندگی
MIN_OPTION_VOLUME = 500

# حداقل موقعیت‌های باز (Open Interest)
MIN_OPEN_INTEREST = 1000

# حداکثر اسپرد مجاز
MAX_SPREAD_PCT = 20

# حداقل روز تا سررسید (جلوگیری از theta burn شدید)
MIN_DTE = 7

# محدوده‌ی Delta مجاز
MIN_DELTA = 0.35
DELTA_MAX = 0.70  # ✅ اصلاح شد (قبلاً 0.75 بود)

TOP_CANDIDATES_COUNT = 3


class OptionSelector:

    def __init__(self, db_path=None):
        # db_path صریح گرفته می‌شه؛ اگه داده نشه، از config فعلی می‌خونه (سازگار با کد قدیمی)
        self.db_path = db_path or config.DATABASE_NAME
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._historical_volatility = compute_historical_volatility(self.db_path)

    def _fetch_candidates(self, wanted_type, limit):
        self.cursor.execute(
            """
            SELECT
                o.symbol,
                o.option_type,
                o.stock_price,
                o.option_price,
                o.strike_price,
                o.expire_date,
                o.days_to_expire,
                o.volume,
                o.open_interest
            FROM options o
            INNER JOIN (
                SELECT symbol, MAX(id) AS max_id
                FROM options
                WHERE option_type = ?
                GROUP BY symbol
            ) latest
            ON o.symbol = latest.symbol AND o.id = latest.max_id
            WHERE o.volume >= ?
            AND o.open_interest >= ?
            AND o.days_to_expire >= ?
            ORDER BY o.volume DESC
            LIMIT ?
            """,
            (wanted_type, MIN_OPTION_VOLUME, MIN_OPEN_INTEREST, MIN_DTE, limit)
        )
        return self.cursor.fetchall()

    def _analyze_row(self, row, override_price=None, current_stock_price=None):
        (
            symbol,
            option_type,
            stock_price,
            option_price,
            strike_price,
            expire_date,
            days_to_expire,
            volume,
            open_interest
        ) = row

        if override_price is not None and override_price > 0:
            option_price = override_price

        if current_stock_price is not None and current_stock_price > 0:
            stock_price = current_stock_price

        engine = OptionEngine()
        option_data = engine.analyze(
            stock_price=float(stock_price),
            strike_price=float(strike_price),
            option_price=float(option_price),
            days_to_expire=int(days_to_expire),
            option_type=option_type,
            volume=float(volume),
            historical_volatility=self._historical_volatility
        )

        option_data.update({
            "symbol": symbol,
            "option_type": option_type,
            "expire_date": expire_date,
            "open_interest": open_interest
        })

        return option_data

    def get_top_candidates(self, stock_action="WATCH", current_stock_price=None, top_n=TOP_CANDIDATES_COUNT):
        if stock_action == "BUY":
            wanted_type = "CALL"
        elif stock_action == "SELL":
            wanted_type = "PUT"
        else:
            return []

        rows = self._fetch_candidates(wanted_type, limit=20)
        candidates = []

        for row in rows:
            analyzed_item = self._analyze_row(row, current_stock_price=current_stock_price)

            # فیلتر داده‌های نامعتبر
            candidate_delta = abs(analyzed_item.get("delta", 0))
            
            if (
                analyzed_item.get("time_value", 0) >= 0
                and candidate_delta >= MIN_DELTA
                and candidate_delta <= DELTA_MAX  # ✅ اضافه شد
            ):
                candidates.append(analyzed_item)

        # ✅ امتیازدهی هوشمند
        def score_option(opt):
            score = 0
            
            # 1. Risk/Reward (وزن 40%)
            rr = opt.get("risk_reward_ratio", 0)
            if rr > 2.5:
                score += 50
            elif rr > 2.0:
                score += 40
            elif rr > 1.5:
                score += 30
            elif rr > 1.0:
                score += 20
            elif rr > 0.5:
                score += 10
            else:
                score -= 20
            
            # 2. فاصله از قیمت (ATM بهتر)
            distance = abs(opt.get("distance_pct", 0))
            if distance < 3:
                score += 25
            elif distance < 5:
                score += 15
            elif distance < 10:
                score += 5
            elif distance > 15:
                score -= 25
            
            # 3. Delta مناسب
            delta = abs(opt.get("delta", 0))
            if 0.45 <= delta <= 0.65:
                score += 20
            elif 0.35 <= delta < 0.45 or 0.65 < delta <= 0.70:
                score += 10
            else:
                score -= 15
            
            # 4. جریمه IV Crush
            if opt.get("iv_crush_risk"):
                iv_ratio = opt.get("iv_premium_ratio", 1)
                if iv_ratio > 4.0:
                    score -= 40
                elif iv_ratio > 2.5:
                    score -= 25
            
            # 5. Valuation
            val = opt.get("valuation", "")
            if val == "UNDERVALUED":
                score += 15
            elif val == "OVERVALUED":
                score -= 15
            
            return score

        candidates.sort(key=score_option, reverse=True)

        return candidates[:top_n]

    def run(
        self,
        stock_action="WATCH",
        stock_confidence=0,
        current_stock_price=None
    ):
        if stock_action == "BUY":
            wanted_type = "CALL"
        elif stock_action == "SELL":
            wanted_type = "PUT"
        else:
            print("STOCK ACTION IS WATCH -> NO OPTION SELECTED")
            return None

        rows = self._fetch_candidates(wanted_type, limit=15)

        if not rows:
            print(
                "NO VALID OPTION DATA FOR", wanted_type,
                f"(نیاز به حجم حداقل {MIN_OPTION_VOLUME}، OI حداقل {MIN_OPEN_INTEREST} "
                f"و حداقل {MIN_DTE} روز تا سررسید)"
            )
            return None

        analyzed = [
            self._analyze_row(row, current_stock_price=current_stock_price)
            for row in rows
        ]

        # ✅ امتیازدهی هوشمند (به جای فقط risk_reward)
        def score_option(opt):
            score = 0
            
            # 1. Risk/Reward (وزن 40%)
            rr = opt.get("risk_reward_ratio", 0)
            if rr > 2.5:
                score += 50
            elif rr > 2.0:
                score += 40
            elif rr > 1.5:
                score += 30
            elif rr > 1.0:
                score += 20
            elif rr > 0.5:
                score += 10
            else:
                score -= 20
            
            # 2. فاصله از قیمت (ATM بهتر از Deep ITM)
            distance = abs(opt.get("distance_pct", 0))
            if distance < 3:      # نزدیک ATM
                score += 25
            elif distance < 5:
                score += 15
            elif distance < 10:
                score += 5
            elif distance > 15:   # Deep ITM/OTM
                score -= 25
            
            # 3. Delta مناسب (0.45-0.65 ایده‌آل)
            delta = abs(opt.get("delta", 0))
            if 0.45 <= delta <= 0.65:
                score += 20
            elif 0.35 <= delta < 0.45 or 0.65 < delta <= 0.70:
                score += 10
            else:
                score -= 15
            
            # 4. جریمه IV Crush
            if opt.get("iv_crush_risk"):
                iv_ratio = opt.get("iv_premium_ratio", 1)
                if iv_ratio > 4.0:
                    score -= 40  # EXTREME
                elif iv_ratio > 2.5:
                    score -= 25
            
            # 5. Valuation
            val = opt.get("valuation", "")
            if val == "UNDERVALUED":
                score += 15
            elif val == "OVERVALUED":
                score -= 15
            
            return score

        analyzed.sort(key=score_option, reverse=True)

        option_data = None
        selected_row = None
        bid_ask = None
        spread_pct = None

        for candidate in analyzed:

            candidate_row = next(
                row for row in rows
                if row[0] == candidate["symbol"]
            )

            # ۱. فیلتر Deep ITM
            candidate_delta = abs(candidate.get("delta", 0))
            if candidate_delta > DELTA_MAX:
                print(
                    f"SKIPPED {candidate['symbol']}: "
                    f"Deep ITM delta {candidate_delta:.3f} > {DELTA_MAX} (بدون اهرم واقعی)"
                )
                continue

            # ۲. فیلتر حداقل Delta
            if candidate_delta < MIN_DELTA:
                print(
                    f"SKIPPED {candidate['symbol']}: "
                    f"Delta خیلی پایین ({candidate_delta:.3f} < {MIN_DELTA})"
                )
                continue

            # ۳. بررسی Bid/Ask لحظه‌ای
            candidate_bid_ask = get_option_bid_ask(candidate["symbol"], self.db_path)

            if not candidate_bid_ask or not candidate_bid_ask.get("ask") or not candidate_bid_ask.get("bid"):
                print(f"SKIPPED {candidate['symbol']}: داده‌ی Bid/Ask موجود نیست")
                continue

            ask = candidate_bid_ask["ask"]
            bid = candidate_bid_ask["bid"]

            if ask <= 0 or bid <= 0:
                print(f"SKIPPED {candidate['symbol']}: قیمت Bid/Ask نامعتبر")
                continue

            # ۴. بررسی اسپرد
            this_spread_pct = ((ask - bid) / ask) * 100

            if this_spread_pct > MAX_SPREAD_PCT:
                print(
                    f"SKIPPED {candidate['symbol']}: "
                    f"اسپرد خیلی زیاد ({round(this_spread_pct, 1)}% > {MAX_SPREAD_PCT}%)"
                )
                continue

            # ۵. تحلیل مجدد با قیمت Ask
            temp_option_data = self._analyze_row(
                candidate_row,
                override_price=ask,
                current_stock_price=current_stock_price
            )

            # ۶. فیلتر ارزش زمانی منفی
            if temp_option_data.get("time_value", 0) < 0:
                print(
                    f"SKIPPED {candidate['symbol']}: "
                    f"ارزش زمانی منفی ({temp_option_data.get('time_value')})"
                )
                continue

            option_data = temp_option_data
            selected_row = candidate_row
            bid_ask = candidate_bid_ask
            spread_pct = this_spread_pct

            option_data["bid_price"] = bid
            option_data["ask_price"] = ask
            option_data["price_source"] = "صف فروش (Ask)"
            option_data["spread_pct"] = spread_pct
            break

        if option_data is None:
            print("همه کاندیدها رد شدند (هیچ آپشن واجد شرایط نیست) ->", wanted_type)
            return None

        decision = OptionDecision().decide(
            stock_action,
            stock_confidence,
            option_data
        )

        print("=" * 60)
        print("AHRAM OPTION SELECTOR V6 (اصلاح‌شده)")
        print("=" * 60)
        print("SYMBOL:", option_data["symbol"])
        print("TYPE:", option_data["option_type"])
        print("STOCK:", option_data["stock_price"])
        print("STRIKE:", option_data["strike_price"])
        print("OPTION PRICE:", option_data["option_price"], f"({option_data['price_source']})")
        print("BID/ASK:", option_data.get("bid_price"), "/", option_data.get("ask_price"))

        if option_data.get("spread_pct") is not None:
            print("SPREAD:", f"{round(option_data['spread_pct'], 1)}%")

        print("FAIR VALUE:", option_data["fair_value"])
        print(
            "VOLATILITY:",
            f"{round(option_data.get('volatility_used', 0) * 100, 1)}%",
            "(تاریخی)" if self._historical_volatility else "(تخمینی)"
        )

        if option_data.get("implied_volatility") is not None:
            print(
                "IMPLIED VOL:",
                f"{round(option_data['implied_volatility'] * 100, 1)}%",
                f"| IV/HV ratio: {option_data.get('iv_premium_ratio')}x"
            )

        if option_data.get("iv_crush_risk"):
            print("⚠️ IV CRUSH RISK: آپشن در حباب نوسان است")

        print("DELTA:", option_data["delta"])
        print("VALUATION:", option_data["valuation"])
        print("DISTANCE:", f"{option_data['distance_pct']}%")
        print("RISK/REWARD:", option_data["risk_reward_ratio"])
        print("PROB OF PROFIT:", f"{option_data['probability_of_profit']}%")

        print("FINAL ACTION:", decision["action"])
        print("CONFIDENCE:", decision["confidence"])

        print("REASONS:")
        for reason in decision["reasons"]:
            print("-", reason)

        print("-" * 60)

        decision.update(option_data)

        return decision

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    selector = OptionSelector()

    result = selector.run(
        stock_action="BUY",
        stock_confidence=45
    )

    print(result)

    candidates = selector.get_top_candidates("BUY")

    print("\nTOP CANDIDATES:")
    for c in candidates:
        print(
            c["symbol"],
            f"R/R={c['risk_reward_ratio']:.2f}",
            f"Δ={c.get('delta', 0):.2f}",
            f"Dist={c.get('distance_pct', 0):.1f}%"
        )

    selector.close()