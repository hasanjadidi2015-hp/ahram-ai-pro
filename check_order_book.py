# -*- coding: utf-8 -*-
"""
چک سریع order_book - برای دیباگ صف برعکس
اجرا: python check_order_book.py
خروجی را کپی کن بفرست
"""
import sqlite3, os, glob

DBS = [
    ("اهرم", "ahram_v2.db"),
    ("وبملت", "webmellt.db"),
    ("شستا", "shasta.db"),
    ("اهرم V5", "ahram_v2_v5.db" if os.path.exists("ahram_v2_v5.db") else "ahram_v5.db"),
    ("وبملت V5", "webmellt_v5.db"),
    ("شستا V5", "shasta_v5.db"),
]

def check_one(name, db):
    print(f"\n{'='*60}")
    print(f"{name} -> {db}")
    if not os.path.exists(db):
        print("  ❌ فایل DB وجود ندارد")
        return
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_book'")
        if not cur.fetchone():
            print("  ❌ جدول order_book وجود ندارد - کالکتور اجرا نشده")
            conn.close()
            return
        cur.execute("SELECT COUNT(*) FROM order_book")
        cnt = cur.fetchone()[0]
        print(f"  تعداد ردیف: {cnt}")
        if cnt==0:
            print("  ⚠️ جدول خالی است")
            conn.close()
            return
        cur.execute("SELECT time FROM order_book ORDER BY id DESC LIMIT 1")
        lt = cur.fetchone()[0]
        print(f"  آخرین زمان: {lt}")
        cur.execute("SELECT time, level, buy_price, sell_price, buy_volume, sell_volume, buy_count, sell_count FROM order_book WHERE time=? ORDER BY level ASC", (lt,))
        rows = cur.fetchall()
        if not rows:
            print("  ⚠️ با time فیلتر نشد، 5 ردیف آخر:")
            cur.execute("SELECT time, level, buy_price, sell_price, buy_volume, sell_volume, buy_count, sell_count FROM order_book ORDER BY id DESC LIMIT 5")
            rows = cur.fetchall()
        total_buy_vol = sum(r[4] or 0 for r in rows)
        total_sell_vol = sum(r[5] or 0 for r in rows)
        total_buy_cnt = sum(r[6] or 0 for r in rows)
        total_sell_cnt = sum(r[7] or 0 for r in rows)
        best_buy = rows[0][2] if rows else 0
        best_sell = rows[0][3] if rows else 0
        print(f"  ردیف‌های آخرین snapshot ({len(rows)} ردیف):")
        for r in rows:
            print(f"    level={r[1]} buy_price={r[2]} sell_price={r[3]} buy_vol={r[4]} sell_vol={r[5]} buy_cnt={r[6]} sell_cnt={r[7]}")
        print(f"  جمع: buy_vol={total_buy_vol} sell_vol={total_sell_vol} buy_cnt={total_buy_cnt} sell_cnt={total_sell_cnt}")
        print(f"  بهترین: buy={best_buy} sell={best_sell}")
        # منطق جدید
        buy_empty = (total_buy_vol==0 and total_buy_cnt==0)
        sell_empty = (total_sell_vol==0 and total_sell_cnt==0)
        if best_buy==0:
            buy_empty = buy_empty or (total_buy_vol==0)
        if best_sell==0:
            sell_empty = sell_empty or (total_sell_vol==0)
        if buy_empty and sell_empty:
            state="NO_DATA"
        elif sell_empty and not buy_empty:
            state="LOCKED_BUY_QUEUE 🔥 صف خرید"
        elif buy_empty and not sell_empty:
            state="LOCKED_SELL_QUEUE 🧊 صف فروش"
        else:
            imb = (total_buy_vol - total_sell_vol)/(total_buy_vol+total_sell_vol)*100 if (total_buy_vol+total_sell_vol)>0 else 0
            state=f"TWO_SIDED imb={imb:+.1f}%"
        print(f"  👉 تشخیص جدید: {state}")
        # منطق قدیم (فقط قیمت)
        old_buy = any((r[2] or 0)>0 for r in rows)
        old_sell = any((r[3] or 0)>0 for r in rows)
        if not old_buy and not old_sell:
            old_state="NO_DATA"
        elif not old_sell:
            old_state="LOCKED_BUY_QUEUE (قدیم)"
        elif not old_buy:
            old_state="LOCKED_SELL_QUEUE (قدیم)"
        else:
            old_state="TWO_SIDED (قدیم)"
        print(f"  👉 تشخیص قدیم (فقط قیمت): {old_state}")
        conn.close()
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        import traceback; traceback.print_exc()

if __name__=="__main__":
    print("🔍 بررسی order_book برای دیباگ صف برعکس")
    print("زمان اجرا: بازار شنبه تا چهارشنبه 08:45-12:30")
    for name, db in DBS:
        check_one(name, db)
    print("\n" + "="*60)
    print("خروجی بالا را کپی کن بفرست تا دقیق بگم مشکل از کجاست")
