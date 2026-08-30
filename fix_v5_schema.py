# -*- coding: utf-8 -*-
"""
Migration fix for V5 DBs - drops broken max_pain_history / iv_history
created by old create_v5_dbs.py (incomplete columns, no ALTER self-repair).

Run once after updating to fixed create_v5_dbs.py
"""
import sqlite3, os

DBS = ["ahram_v2_v5.db", "webmellt_v5.db", "shasta_v5.db"]

EXPECTED_MAX_PAIN_COLS = {
    "time", "latest_options_time", "underlying_symbol", "expiry",
    "stock_price", "max_pain_strike", "current_distance_pct",
    "total_pain", "contracts_count", "contracts_with_oi",
    "data_quality", "candidate_strikes", "details"
}

EXPECTED_IV_COLS = {"date", "atm_iv", "updated_at"}

for db_path in DBS:
    if not os.path.exists(db_path):
        print(f"⏭️ {db_path} not found - skip")
        continue
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check max_pain_history
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='max_pain_history'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(max_pain_history)")
            cols = {r[1] for r in cur.fetchall()}
            missing = EXPECTED_MAX_PAIN_COLS - cols
            if missing:
                print(f"⚠️ {db_path}: max_pain_history missing {missing} -> DROP")
                cur.execute("DROP TABLE max_pain_history")
                conn.commit()
                print(f"  ✅ Dropped max_pain_history in {db_path} - will be recreated by max_pain.py")
            else:
                print(f"✅ {db_path}: max_pain_history OK ({len(cols)} cols)")
        else:
            print(f"✅ {db_path}: max_pain_history not exists - OK (will be created by owner)")
    except Exception as e:
        print(f"❌ {db_path} max_pain check error: {e}")

    # Check iv_history
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='iv_history'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(iv_history)")
            cols = {r[1] for r in cur.fetchall()}
            missing = EXPECTED_IV_COLS - cols
            if missing or cols != EXPECTED_IV_COLS:
                # if any extra check - if not exact expected, drop to be safe if incomplete
                # But allow exact match only
                if cols != EXPECTED_IV_COLS:
                    # Check if it's incomplete old version
                    if len(cols) < 3 or missing:
                        print(f"⚠️ {db_path}: iv_history incomplete {cols} -> DROP")
                        cur.execute("DROP TABLE iv_history")
                        conn.commit()
                        print(f"  ✅ Dropped iv_history in {db_path} - will be recreated by iv_rank.py")
                    else:
                        print(f"✅ {db_path}: iv_history OK but extra cols {cols}")
                else:
                    print(f"✅ {db_path}: iv_history OK")
            else:
                print(f"✅ {db_path}: iv_history OK")
        else:
            print(f"✅ {db_path}: iv_history not exists - OK")
    except Exception as e:
        print(f"❌ {db_path} iv check error: {e}")

    conn.close()

print("\n✅ Migration done - now run report_v5.py to recreate tables correctly")
