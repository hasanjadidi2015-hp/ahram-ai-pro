# -*- coding: utf-8 -*-
"""AHRAM LEARNING CORE - هوش مصنوعی + ردیابی زنده‌ی خروج"""
import os
import sys
import math
import pickle
import sqlite3
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config

MODEL_FILE = "ahram_ml_model.pkl"
LAST_TRAIN_FILE = "ahram_last_train.txt"
MIN_SAMPLES_TO_TRAIN = 20
STALE_PENDING_DAYS = 4


def ensure_tables():
    conn = sqlite3.connect(config.DATABASE_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT, symbol TEXT, option_type TEXT, direction TEXT,
            entry_price REAL, stop_loss REAL, target1 REAL, target2 REAL,
            stock_action TEXT, stock_confidence REAL, stock_score REAL,
            valuation TEXT, distance_pct REAL, risk_reward_ratio REAL,
            delta REAL, days_to_expire INTEGER, composite_score INTEGER,
            signal_type TEXT, outcome TEXT, outcome_pct REAL, evaluated_at TEXT
        )
    """)
    try:
        cur.execute("ALTER TABLE signal_history ADD COLUMN symbol_short TEXT")
        conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()


def log_signal(signal):
    ensure_tables()
    od = signal.get("option_decision") or {}
    if signal.get("type") != "BUY" or not od:
        return None
    symbol = od.get("symbol")
    conn = sqlite3.connect(config.DATABASE_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id FROM signal_history WHERE symbol=? AND outcome IN ('PENDING','T1_HIT') LIMIT 1", (symbol,))
    if cur.fetchone():
        conn.close()
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO signal_history
        (time, symbol, option_type, direction, entry_price, stop_loss, target1, target2,
         stock_action, stock_confidence, stock_score, valuation, distance_pct,
         risk_reward_ratio, delta, days_to_expire, composite_score, signal_type, outcome, symbol_short)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING', ?)
    """, (
        now, symbol, od.get("option_type"), "BUY",
        od.get("option_price"), od.get("stop_loss"), od.get("target1"), od.get("target2"),
        signal.get("stock_action"),
        signal.get("stock_confidence") or od.get("confidence"),
        signal.get("stock_score"),
        od.get("valuation"), od.get("distance_pct"),
        od.get("risk_reward_ratio"), od.get("delta"),
        od.get("days_to_expire"), signal.get("score"), signal.get("type"),
        od.get("symbol_short"),
    ))
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    print(f"[LEARN] سیگنال جدید ثبت شد (#{row_id}: {symbol})")
    return row_id


def check_live_exits():
    ensure_tables()
    conn = sqlite3.connect(config.DATABASE_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, symbol, entry_price, stop_loss, target1, target2, outcome
        FROM signal_history
        WHERE outcome IN ('PENDING', 'T1_HIT')
          AND entry_price IS NOT NULL AND stop_loss IS NOT NULL AND target1 IS NOT NULL
    """)
    open_signals = cur.fetchall()
    alerts = []
    for sid, symbol, entry, stop, t1, t2, outcome in open_signals:
        entry, stop, t1 = float(entry), float(stop), float(t1)
        t2 = float(t2) if t2 else t1
        row = cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,)).fetchone()
        if not row or not row[0]:
            continue
        try:
            price = float(row[0])
        except (ValueError, TypeError):
            continue
        _ss = cur.execute("SELECT symbol_short FROM signal_history WHERE id=?", (sid,)).fetchone()
        if _ss and _ss[0]:
            _sr = cur.execute("SELECT option_price FROM options WHERE symbol=? ORDER BY id DESC LIMIT 1", (_ss[0],)).fetchone()
            if _sr and _sr[0]:
                try:
                    price = price - float(_sr[0])
                except (ValueError, TypeError):
                    pass
        if price <= 0:
            continue
        pct = round(((price - entry) / entry) * 100, 1)
        if price >= t2:
            cur.execute("UPDATE signal_history SET outcome='WIN', outcome_pct=?, evaluated_at=? WHERE id=?",
                        (pct, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sid))
            alerts.append({"type": "EXIT_WIN", "symbol": symbol,
                "text": f"✅ سیگنال خروج (هدف دوم)\nنماد: {symbol}\nقیمت فعلی: {int(price)} (هدف: {int(t2)})\nسود: {pct}%\n→ بقیه حجم رو بفروش"})
        elif price <= stop:
            cur.execute("UPDATE signal_history SET outcome='LOSS', outcome_pct=?, evaluated_at=? WHERE id=?",
                        (pct, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sid))
            alerts.append({"type": "EXIT_STOP", "symbol": symbol,
                "text": f"🛑 سیگنال خروج (حد ضرر)\nنماد: {symbol}\nقیمت فعلی: {int(price)} (حد ضرر: {int(stop)})\nزیان: {pct}%\n→ فوراً خارج شو"})
        elif price >= t1 and outcome == "PENDING":
            cur.execute("UPDATE signal_history SET outcome='T1_HIT', outcome_pct=? WHERE id=?", (pct, sid))
            alerts.append({"type": "SELL_HALF", "symbol": symbol,
                "text": f"🎯 هدف اول لمس شد\nنماد: {symbol}\nقیمت فعلی: {int(price)} (هدف اول: {int(t1)})\nسود: {pct}%\n→ نصف حجم رو بفروش، بقیه نگه‌دار"})
    conn.commit()
    conn.close()
    return alerts


def evaluate_outcomes():
    ensure_tables()
    conn = sqlite3.connect(config.DATABASE_NAME)
    cur = conn.cursor()
    cur.execute("""SELECT id, time, symbol, entry_price, stop_loss, target1
                   FROM signal_history WHERE outcome='PENDING'
                   AND entry_price IS NOT NULL AND stop_loss IS NOT NULL AND target1 IS NOT NULL""")
    pending = cur.fetchall()
    evaluated = 0
    for sid, sig_time, symbol, entry, stop, target in pending:
        cur.execute("SELECT option_price FROM options WHERE symbol=? AND time>? ORDER BY time ASC", (symbol, sig_time))
        rows = cur.fetchall()
        outcome = None
        outcome_pct = None
        for (price,) in rows:
            try:
                p = float(price)
            except (ValueError, TypeError):
                continue
            if p <= 0:
                continue
            if p >= float(target):
                outcome, outcome_pct = "WIN", round(((p - float(entry)) / float(entry)) * 100, 1)
                break
            if p <= float(stop):
                outcome, outcome_pct = "LOSS", round(((p - float(entry)) / float(entry)) * 100, 1)
                break
        if outcome is None:
            try:
                sig_dt = datetime.strptime(sig_time[:19], "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - sig_dt).days >= STALE_PENDING_DAYS:
                    outcome = "INCONCLUSIVE"
            except Exception:
                pass
        if outcome is not None:
            cur.execute("UPDATE signal_history SET outcome=?, outcome_pct=?, evaluated_at=? WHERE id=?",
                        (outcome, outcome_pct, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sid))
            evaluated += 1
    conn.commit()
    conn.close()
    if evaluated:
        print(f"[LEARN] {evaluated} سیگنال قدیمی ارزیابی شد.")
    return evaluated


_VAL_MAP = {"UNDERVALUED": 1, "FAIR": 0, "OVERVALUED": -1, "INVALID": -2}
_TYPE_MAP = {"CALL": 1, "PUT": -1}


def _featurize(row):
    (valuation, distance_pct, rr, delta, stock_conf, dte, option_type) = row
    return [
        _VAL_MAP.get(valuation, 0) if valuation else 0,
        float(distance_pct or 0), float(rr or 0), abs(float(delta or 0)),
        float(stock_conf or 0), float(dte or 0),
        _TYPE_MAP.get(option_type, 0) if option_type else 0,
    ]


def train_model():
    ensure_tables()
    conn = sqlite3.connect(config.DATABASE_NAME)
    cur = conn.cursor()
    cur.execute("""SELECT valuation, distance_pct, risk_reward_ratio, delta,
                          stock_confidence, days_to_expire, option_type, outcome
                   FROM signal_history WHERE outcome IN ('WIN', 'LOSS')""")
    rows = cur.fetchall()
    conn.close()
    if len(rows) < MIN_SAMPLES_TO_TRAIN:
        return {"trained": False, "samples": len(rows), "needed": MIN_SAMPLES_TO_TRAIN,
                "message": f"داده‌ی کافی نیست ({len(rows)}/{MIN_SAMPLES_TO_TRAIN})."}
    X = [_featurize(r[:7]) for r in rows]
    y = [1 if r[7] == "WIN" else 0 for r in rows]
    try:
        from sklearn.tree import DecisionTreeClassifier
        model = DecisionTreeClassifier(max_depth=4, min_samples_leaf=3, class_weight="balanced")
        model.fit(X, y)
        with open(MODEL_FILE, "wb") as f:
            pickle.dump(model, f)
        with open(LAST_TRAIN_FILE, "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        wins = sum(y)
        accuracy = round(model.score(X, y) * 100, 1)
        return {"trained": True, "samples": len(rows),
                "win_rate": round(wins / len(y) * 100, 1), "accuracy": accuracy,
                "message": f"مدل آموزش داده شد روی {len(rows)} سیگنال | نرخ برد {round(wins/len(y)*100,1)}% | دقت {accuracy}%"}
    except ImportError:
        wins = sum(y)
        wr = wins / len(y)
        with open(MODEL_FILE, "wb") as f:
            pickle.dump({"type": "baseline", "win_rate": wr, "n": len(y)}, f)
        return {"trained": True, "samples": len(rows),
                "win_rate": round(wr * 100, 1), "accuracy": round(wr * 100, 1),
                "message": f"مدل پایه ساخته شد | نرخ برد {round(wr*100,1)}%"}


def predict_win_probability(option_data):
    if not os.path.exists(MODEL_FILE):
        return None
    try:
        with open(MODEL_FILE, "rb") as f:
            model = pickle.load(f)
    except Exception:
        return None
    features = _featurize((
        option_data.get("valuation"), option_data.get("distance_pct"),
        option_data.get("risk_reward_ratio"), option_data.get("delta"),
        option_data.get("confidence") or option_data.get("stock_confidence") or 0,
        option_data.get("days_to_expire"), option_data.get("option_type"),
    ))
    if isinstance(model, dict) and model.get("type") == "baseline":
        return round(model.get("win_rate", 0.5) * 100, 1)
    try:
        proba = model.predict_proba([features])[0]
        classes = list(model.classes_)
        if 1 in classes:
            return round(proba[classes.index(1)] * 100, 1)
        return None
    except Exception:
        return None


def get_ml_adjustment(option_data):
    p = predict_win_probability(option_data)
    if p is None:
        return 0, "هوش مصنوعی: هنوز داده‌ی کافی نیست"
    if p >= 65:
        return 8, f"الگوی موفق مشابه (احتمال برد {p}%)"
    if p <= 35:
        return -12, f"الگوی ناموفق مشابه (احتمال برد {p}%)"
    return 0, f"بدون سیگنال قوی (احتمال برد {p}%)"


def needs_daily_update():
    if not os.path.exists(LAST_TRAIN_FILE):
        return True
    try:
        with open(LAST_TRAIN_FILE) as f:
            last = datetime.strptime(f.read().strip()[:10], "%Y-%m-%d")
        return (datetime.now() - last).days >= 1
    except Exception:
        return True


def daily_update(force=False):
    if not force and not needs_daily_update():
        return None
    print("\n" + "=" * 50)
    print("🧠 AHRAM LEARNING CORE - به‌روزرسانی روزانه")
    print("=" * 50)
    evaluated = evaluate_outcomes()
    stats = train_model()
    print("ارزیابی نتایج:", evaluated, "سیگنال")
    print("وضعیت مدل:", stats["message"])
    try:
        conn = sqlite3.connect(config.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome='WIN'"); wins = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome='LOSS'"); losses = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE outcome IN ('PENDING','T1_HIT')"); pending = cur.fetchone()[0]
        conn.close()
        total = wins + losses
        if total:
            print(f"تاریخچه: {wins} برد / {losses} باخت ({round(wins/total*100,1)}% برد) | {pending} باز")
        else:
            print(f"هنوز ارزیابی‌شده نیست | {pending} باز")
    except Exception:
        pass
    print("=" * 50)
    return stats


if __name__ == "__main__":
    daily_update(force=True)
    print("\nبررسی زنده‌ی خروج‌ها:")
    for a in check_live_exits():
        print("-", a["text"])