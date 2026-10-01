# -*- coding: utf-8 -*-
from ahram_pro import _calculate_targets as f
opt = {"option_price": 4000, "days_to_expire": 22, "option_type": "CALL"}
v = {"auto_sl": {"sl_pct": 5}}
for sym, code in [("AH", "17914401175772326"), ("OT", "778253364357513")]:
    floor = 0.12 if code.startswith("179") else 0.10
    r = f(opt, "BUY_CALL", v, None, floor)
    print(sym, "sl_pct:", r["stop_loss_pct"], "sl:", r["stop_loss"])
v2 = {"auto_sl": {"sl_pct": 15}}
r = f(opt, "BUY_CALL", v2, None, 0.12)
print("wide stays:", r["stop_loss_pct"])
print("DONE")