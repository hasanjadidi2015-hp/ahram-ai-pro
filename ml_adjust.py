# -*- coding: utf-8 -*-
"""
تنظیم امتیاز سیگنال بر پایه‌ی یادگیری ماشین از نتیجه‌ی معاملات گذشته.

این ماژول جایگزین بخش ML از learning_core.py می‌شه (که مخصوص agent.py بود
و روی یه جدول جدا کار می‌کرد). این نسخه مستقیم از جدول signal_history خودِ
ahram_pro.py می‌خونه -- همون جایی که outcome (WIN/LOSS) قبلاً توسط
dashboard._update_pending_outcomes ارزیابی می‌شه -- بدون نیاز به schema جدا.

هر نماد فایل مدل جدای خودش رو داره (بر پایه‌ی اسم دیتابیس)، که یه باگ قبلی
(مدل مشترک بین همه‌ی نمادها که همدیگه رو بازنویسی می‌کردن) رو هم رعایت می‌کنه.
"""
import os
import json
import pickle
import sqlite3
from datetime import datetime

MIN_SAMPLES = 15


def _model_paths(db_path):
    base = os.path.splitext(os.path.basename(db_path))[0]
    return f"{base}_ml_model.pkl", f"{base}_ml_last_train.txt"


def _extract_features(option_decision, score):
    """ویژگی‌های عددی که برای پیش‌بینی احتمال برد استفاده می‌شن."""
    try:
        return [
            float(option_decision.get("confidence", 50)),
            float(option_decision.get("delta", 0.5)),
            float(option_decision.get("iv_premium_ratio", 1.0)),
            float(option_decision.get("probability_of_profit", 50)),
            float(option_decision.get("distance_pct", 0)),
            float(score),
        ]
    except Exception:
        return None


def train_model(db_path):
    """مدل رو از سیگنال‌های ارزیابی‌شده‌ی (WIN/LOSS) همین دیتابیس آموزش می‌ده."""
    model_file, last_train_file = _model_paths(db_path)
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT details, composite_score, outcome FROM signal_history "
            "WHERE outcome IN ('WIN','LOSS') AND details IS NOT NULL AND details != '' "
            "AND id IN (SELECT MIN(id) FROM signal_history WHERE outcome IN ('WIN','LOSS') "
            "AND position_id IS NOT NULL GROUP BY position_id)"
        )
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return {"trained": False, "message": f"خطا خواندن دیتابیس: {e}"}

    X, y = [], []
    for details_json, score, outcome in rows:
        try:
            d = json.loads(details_json)
        except Exception:
            continue
        opt = d.get("option") or {}
        feats = _extract_features(opt, score if score is not None else 50)
        if feats is None:
            continue
        X.append(feats)
        y.append(1 if outcome == "WIN" else 0)

    if len(X) < MIN_SAMPLES:
        return {"trained": False, "message": f"داده کافی نیست ({len(X)}/{MIN_SAMPLES})"}

    try:
        from sklearn.tree import DecisionTreeClassifier
        model = DecisionTreeClassifier(max_depth=4, min_samples_leaf=3, class_weight="balanced")
        model.fit(X, y)
        with open(model_file, "wb") as f:
            pickle.dump(model, f)
    except ImportError:
        wr = sum(y) / len(y)
        with open(model_file, "wb") as f:
            pickle.dump({"type": "baseline", "win_rate": wr}, f)

    with open(last_train_file, "w") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    wins = sum(y)
    return {"trained": True, "samples": len(X),
            "win_rate": round(wins / len(y) * 100, 1),
            "message": f"مدل روی {len(X)} سیگنال آموزش دید | نرخ برد {round(wins/len(y)*100,1)}%"}


def needs_daily_update(db_path):
    _, last_train_file = _model_paths(db_path)
    if not os.path.exists(last_train_file):
        return True
    try:
        with open(last_train_file) as f:
            last = datetime.strptime(f.read().strip()[:10], "%Y-%m-%d")
        return (datetime.now() - last).days >= 1
    except Exception:
        return True


def get_ml_adjustment(option_decision, score, db_path):
    """برمی‌گردونه (تعدیل امتیاز, دلیل) یا (0, None) اگه مدلی موجود نباشه."""
    model_file, _ = _model_paths(db_path)
    if not os.path.exists(model_file):
        return 0, None
    feats = _extract_features(option_decision, score)
    if feats is None:
        return 0, None
    try:
        with open(model_file, "rb") as f:
            model = pickle.load(f)
        if isinstance(model, dict) and model.get("type") == "baseline":
            p = model["win_rate"]
        else:
            p = model.predict_proba([feats])[0][1]
        if p >= 0.65:
            return 10, f"مدل یادگیری: احتمال برد بالا ({round(p*100)}%)"
        elif p <= 0.35:
            return -10, f"مدل یادگیری: احتمال برد پایین ({round(p*100)}%)"
        return 0, None
    except Exception:
        return 0, None