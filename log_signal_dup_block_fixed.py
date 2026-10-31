# جلوگیری از تکرار و کولداون بعد از زیان (نسخه‌ی اصلاح‌شده: اتصال تا آخرین کوئری باز می‌ماند)
    _c = None
    try:
        _c = sqlite3.connect(db_name)
        # فقط آخرین خرید همین نماد رو نگاه می‌کنیم (نه آخرین ردیف هر نوعی)
        _last = _c.execute(
            "SELECT signal_type, time FROM signal_history WHERE symbol=? "
            "AND signal_type IN ('BUY_CALL','BUY_PUT') ORDER BY id DESC LIMIT 1",
            (symbol_name,),
        ).fetchone()
        if _last and _last[0] == signal.get("type") and signal.get("type") in ("BUY_CALL", "BUY_PUT"):
            _mins = (datetime.now() - datetime.strptime(str(_last[1])[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
            if _mins < 30:
                state.log(f"  ⏭ {symbol_name}: {signal.get('type')} تکراریه (آخرین بار {int(_mins)} دقیقه پیش) -- ثبت نشد", "INFO")
                return
        # کولداون بعد از زیان: همین نماد و همین نوع خرید، به زیان بسته شده و کمتر از ۶۰ دقیقه گذشته
        if signal.get("type") in ("BUY_CALL", "BUY_PUT"):
            _loss = _c.execute(
                "SELECT outcome_time FROM signal_history WHERE symbol=? AND signal_type=? "
                "AND outcome='LOSS' AND outcome_time IS NOT NULL ORDER BY id DESC LIMIT 1",
                (symbol_name, signal.get("type")),
            ).fetchone()
            if _loss and _loss[0]:
                _since = (datetime.now() - datetime.strptime(str(_loss[0])[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
                if _since < 60:
                    state.log(f"  ⏭ {symbol_name}: {signal.get('type')} در کولداون بعد از زیان ({int(_since)} دقیقه پیش) -- ثبت نشد", "INFO")
                    return
    except Exception as _dup_e:
        state.log(f"  ⚠️ بررسی تکرار/کولداون ناموفق ({symbol_name}): {_dup_e} -- سیگنال ثبت می‌شه", "WARN")
    finally:
        if _c is not None:
            _c.close()