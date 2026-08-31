# -*- coding: utf-8 -*-
"""
کالکتور همه نمادها برای فیکس order_book - نسخه 2026-08-31
اجرا: python collect_all_orderbooks.py
بعدش: python check_order_book.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from order_book import collect_order_book

SYMBOLS = [
    ("اهرم", "ahram_v2.db", "17914401175772326"),
    ("وبملت", "webmellt.db", "778253364357513"),
    ("شستا", "shasta.db", "2400322364771558"),
]

for name, db, ins in SYMBOLS:
    print(f"\n{'='*50}")
    print(f"📊 جمع‌آوری {name} - {ins}")
    try:
        result = collect_order_book(db_path=db, ins_code=ins)
        if result:
            print(f"✅ {name}: {result['market_state']} | buy={result['best_buy']} sell={result['best_sell']} | buy_vol={result['total_buy_volume']:,.0f} sell_vol={result['total_sell_volume']:,.0f}")
        else:
            print(f"❌ {name}: داده نگرفت")
    except Exception as e:
        print(f"❌ خطا {name}: {e}")
        import traceback; traceback.print_exc()

print("\n✅ تمام شد - حالا python check_order_book.py را بزن")
