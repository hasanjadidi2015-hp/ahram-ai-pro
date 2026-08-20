# -*- coding: utf-8 -*-
"""
AHRAM AI - ابزارهای قرارداد آپشن
مقایسه قراردادها + زنجیره قرارداد
"""
import sqlite3
from datetime import datetime

import config


class ContractComparison:
    """مقایسه چند قرارداد آپشن"""
    
    def __init__(self, db_name=None):
        self.db = db_name or config.DATABASE_NAME
        self.contracts = []
        self.best_contract = None
    
    def fetch_contracts(self, option_type="CALL", limit=5):
        """دریافت قراردادها برای مقایسه"""
        try:
            conn = sqlite3.connect(self.db)
            cur = conn.cursor()
            
            cur.execute("SELECT MAX(time) FROM options")
            latest = cur.fetchone()[0]
            
            if not latest:
                conn.close()
                return []
            
            cur.execute("""
                SELECT 
                    symbol, option_type, stock_price, option_price,
                    strike_price, days_to_expire, volume, open_interest
                FROM options 
                WHERE time = ? 
                    AND option_type = ?
                    AND option_price > 0
                    AND volume > 100
                ORDER BY volume DESC
                LIMIT ?
            """, (latest, option_type, limit))
            
            rows = cur.fetchall()
            conn.close()
            
            contracts = []
            for row in rows:
                symbol, opt_type, stock_price, option_price, strike_price, dte, volume, oi = row
                
                # محاسبه شاخص‌ها
                stock_price = float(stock_price or 0)
                option_price = float(option_price or 0)
                strike_price = float(strike_price or 0)
                dte = int(dte or 0)
                volume = float(volume or 0)
                oi = float(oi or 0)
                
                if stock_price <= 0 or option_price <= 0:
                    continue
                
                # اهرم
                leverage = stock_price / option_price if option_price > 0 else 0
                
                # فاصله از قیمت فعلی
                distance_pct = abs((strike_price - stock_price) / stock_price * 100) if stock_price > 0 else 0
                
                # ارزش ذاتی
                if opt_type == "CALL":
                    intrinsic = max(0, stock_price - strike_price)
                else:
                    intrinsic = max(0, strike_price - stock_price)
                
                # ارزش زمانی
                time_value = option_price - intrinsic
                
                # نسبت حجم به OI
                vol_oi_ratio = volume / oi if oi > 0 else 0
                
                # امتیازدهی
                score = 0
                
                # حجم بالا = بهتر
                if volume > 10000:
                    score += 30
                elif volume > 5000:
                    score += 20
                elif volume > 1000:
                    score += 10
                
                # OI بالا = بهتر
                if oi > 10000:
                    score += 20
                elif oi > 5000:
                    score += 15
                elif oi > 1000:
                    score += 10
                
                # فاصله نزدیک ATM = بهتر
                if distance_pct < 3:
                    score += 25
                elif distance_pct < 5:
                    score += 15
                elif distance_pct < 10:
                    score += 10
                
                # اهرم بالا = بهتر
                if leverage > 10:
                    score += 15
                elif leverage > 5:
                    score += 10
                elif leverage > 2:
                    score += 5
                
                # ارزش زمانی منطقی
                if time_value > 0 and time_value < option_price * 0.5:
                    score += 10
                
                contracts.append({
                    "symbol": symbol,
                    "option_type": opt_type,
                    "stock_price": stock_price,
                    "option_price": option_price,
                    "strike_price": strike_price,
                    "days_to_expire": dte,
                    "volume": volume,
                    "open_interest": oi,
                    "leverage": round(leverage, 2),
                    "distance_pct": round(distance_pct, 2),
                    "intrinsic": round(intrinsic, 2),
                    "time_value": round(time_value, 2),
                    "vol_oi_ratio": round(vol_oi_ratio, 2),
                    "score": score,
                })
            
            # مرتب‌سازی بر اساس امتیاز
            contracts.sort(key=lambda x: x["score"], reverse=True)
            
            self.contracts = contracts
            if contracts:
                self.best_contract = contracts[0]
            
            return contracts
            
        except Exception as e:
            print(f"[COMPARISON] Error: {e}")
            return []
    
    def print_comparison(self):
        """چاپ مقایسه"""
        if not self.contracts:
            print("❌ قراردادی برای مقایسه وجود ندارد")
            return
        
        print("=" * 80)
        print("📊 مقایسه قراردادهای آپشن")
        print("=" * 80)
        
        print(f"\n{'نماد':<15} {' Strike':<10} {' قیمت':<8} {' روز':<5} {' حجم':<10} {' OI':<10} {' اهرم':<8} {' امتیاز':<6}")
        print("-" * 80)
        
        for c in self.contracts:
            marker = "⭐" if c == self.best_contract else "  "
            print(f"{marker}{c['symbol']:<13} {int(c['strike_price']):>8} {int(c['option_price']):>8} {c['days_to_expire']:>4} {int(c['volume']):>10} {int(c['open_interest']):>10} {c['leverage']:>7}x {c['score']:>5}")
        
        print("-" * 80)
        
        if self.best_contract:
            best = self.best_contract
            print(f"\n🏆 بهترین قرارداد: {best['symbol']}")
            print(f"   Strike: {int(best['strike_price']):,}")
            print(f"   قیمت: {int(best['option_price']):,}")
            print(f"   اهرم: {best['leverage']}x")
            print(f"   حجم: {int(best['volume']):,}")
            print(f"   OI: {int(best['open_interest']):,}")


class ContractChain:
    """زنجیره قراردادهای آپشن"""
    
    def __init__(self, db_name=None):
        self.db = db_name or config.DATABASE_NAME
        self.chain = {}
    
    def fetch_chain(self, symbol_filter=None):
        """دریافت زنجیره قراردادها"""
        try:
            conn = sqlite3.connect(self.db)
            cur = conn.cursor()
            
            cur.execute("SELECT MAX(time) FROM options")
            latest = cur.fetchone()[0]
            
            if not latest:
                conn.close()
                return {}
            
            query = """
                SELECT 
                    symbol, option_type, stock_price, option_price,
                    strike_price, days_to_expire, volume, open_interest
                FROM options 
                WHERE time = ? 
                    AND option_price > 0
                ORDER BY strike_price, option_type
            """
            
            cur.execute(query, (latest,))
            rows = cur.fetchall()
            conn.close()
            
            chain = {}
            for row in rows:
                symbol, opt_type, stock_price, option_price, strike_price, dte, volume, oi = row
                
                if symbol_filter and symbol_filter not in symbol:
                    continue
                
                strike = float(strike_price)
                
                if strike not in chain:
                    chain[strike] = {"CALL": None, "PUT": None}
                
                chain[strike][opt_type] = {
                    "symbol": symbol,
                    "price": float(option_price),
                    "volume": float(volume or 0),
                    "oi": float(oi or 0),
                    "dte": int(dte or 0),
                }
            
            self.chain = chain
            return chain
            
        except Exception as e:
            print(f"[CHAIN] Error: {e}")
            return {}
    
    def print_chain(self, stock_price=None):
        """چاپ زنجیره"""
        if not self.chain:
            print("❌ زنجیره‌ای وجود ندارد")
            return
        
        print("=" * 90)
        print("📊 زنجیره قراردادهای آپشن")
        print("=" * 90)
        
        if stock_price:
            print(f"  قیمت فعلی: {int(stock_price):,}")
        
        print(f"\n{'Strike':<10} {'CALL Price':<12} {'CALL Vol':<10} {'CALL OI':<10} {'PUT Price':<12} {'PUT Vol':<10} {'PUT OI':<10}")
        print("-" * 90)
        
        for strike in sorted(self.chain.keys()):
            call = self.chain[strike].get("CALL")
            put = self.chain[strike].get("PUT")
            
            # علامت ATM
            marker = ""
            if stock_price:
                if abs(strike - stock_price) / stock_price < 0.02:
                    marker = " ← ATM"
            
            call_price = f"{int(call['price']):,}" if call else "-"
            call_vol = f"{int(call['volume']):,}" if call else "-"
            call_oi = f"{int(call['oi']):,}" if call else "-"
            
            put_price = f"{int(put['price']):,}" if put else "-"
            put_vol = f"{int(put['volume']):,}" if put else "-"
            put_oi = f"{int(put['oi']):,}" if put else "-"
            
            print(f"{int(strike):>8} {call_price:>12} {call_vol:>10} {call_oi:>10} {put_price:>12} {put_vol:>10} {put_oi:>10}{marker}")
        
        print("-" * 90)
        print(f"  تعداد کل: {len(self.chain)} strike")


class ProfitPredictor:
    """پیش‌بینی سود آپشن"""
    
    def __init__(self):
        self.scenarios = []
    
    def predict(self, entry_price, strike_price, option_type="CALL", days_to_expire=30, current_stock_price=None):
        """پیش‌بینی سود در سناریوهای مختلف"""
        # سناریوها باید بر اساس قیمت واقعی سهم باشن، نه قیمت اعمال (strike) —
        # وگرنه برای قراردادهای غیر-ATM کاملاً گمراه‌کننده می‌شه.
        base_price = current_stock_price if current_stock_price else strike_price
        if not current_stock_price:
            print("⚠️ قیمت فعلی سهم داده نشده؛ سناریوها بر اساس Strike تخمین زده می‌شن (ممکنه دقیق نباشه)")

        scenarios = []

        # سناریوهای مختلف تغییر قیمت سهم
        stock_changes = [-10, -5, -3, -1, 0, 1, 3, 5, 10]

        for change_pct in stock_changes:
            # قیمت جدید سهم
            new_stock = base_price * (1 + change_pct / 100)
            
            # قیمت تقریبی آپشن (بسیار ساده‌شده)
            if option_type == "CALL":
                intrinsic = max(0, new_stock - strike_price)
            else:
                intrinsic = max(0, strike_price - new_stock)
            
            # ارزش زمانی تقریبی (کاهش با گذشت زمان)
            time_factor = max(0.1, days_to_expire / 30)
            time_value = entry_price * 0.3 * time_factor
            
            # قیمت تقریبی آپشن
            estimated_price = intrinsic + time_value
            
            # سود/ضرر
            profit_pct = (estimated_price - entry_price) / entry_price * 100
            
            scenarios.append({
                "stock_change": change_pct,
                "new_stock": round(new_stock),
                "estimated_option": round(estimated_price),
                "profit_pct": round(profit_pct, 1),
            })
        
        self.scenarios = scenarios
        return scenarios
    
    def print_prediction(self):
        """چاپ پیش‌بینی"""
        if not self.scenarios:
            print("❌ پیش‌بینی‌ای وجود ندارد")
            return
        
        print("=" * 60)
        print("📊 پیش‌بینی سود آپشن")
        print("=" * 60)
        
        print(f"\n{'تغییر سهم':<12} {'قیمت سهم':<12} {'قیمت آپشن':<12} {'سود/ضرر':<10}")
        print("-" * 60)
        
        for s in self.scenarios:
            emoji = "✅" if s["profit_pct"] > 0 else ("❌" if s["profit_pct"] < 0 else "⚪")
            print(f"{s['stock_change']:>+8}% {int(s['new_stock']):>10,} {int(s['estimated_option']):>10,} {emoji} {s['profit_pct']:>+8}%")
        
        print("-" * 60)


# ===== توابع کمکی =====

def compare_contracts(db_name=None, option_type="CALL", limit=5):
    """مقایسه قراردادها"""
    comp = ContractComparison(db_name)
    comp.fetch_contracts(option_type, limit)
    comp.print_comparison()
    return comp.contracts


def show_chain(db_name=None, symbol_filter=None, stock_price=None):
    """نمایش زنجیره"""
    chain = ContractChain(db_name)
    chain.fetch_chain(symbol_filter)
    chain.print_chain(stock_price)
    return chain.chain


def predict_profit(entry_price, strike_price, option_type="CALL", days_to_expire=30, current_stock_price=None):
    """پیش‌بینی سود"""
    predictor = ProfitPredictor()
    predictor.predict(entry_price, strike_price, option_type, days_to_expire, current_stock_price)
    predictor.print_prediction()
    return predictor.scenarios


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("📊 مقایسه قراردادهای CALL")
    print("=" * 60)
    compare_contracts()
    
    print("\n" + "=" * 60)
    print("📊 زنجیره قراردادها")
    print("=" * 60)
    show_chain(stock_price=50800)
    
    print("\n" + "=" * 60)
    print("📊 پیش‌بینی سود")
    print("=" * 60)
    predict_profit(8820, 50000, "CALL", 64)