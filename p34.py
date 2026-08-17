p = 'strategy.py'
s = open(p, encoding='utf-8').read()
a = '        confidence = round((aligned_count / self.TOTAL_INDICATORS) * 100)'
if 'EMA/MACD/ADX bonuses' not in s:
    bonus = ('        # EMA/MACD/ADX bonuses\n'
             '        for _sig,_name in [(ema_signal,"EMA"),(macd_signal,"MACD"),(adx_signal,"ADX")]:\n'
             '            if _sig=="BULLISH": score+=5; reasons.append(_name+" bonus")\n'
             '            elif _sig=="BEARISH": score-=5\n\n' + a)
    s = s.replace(a, bonus, 1)
b_old = '            ("BOLLINGER", bollinger_signal, self.boll.strength),\n        ]'
if '("EMA"' not in s:
    b_new = ('            ("BOLLINGER", bollinger_signal, self.boll.strength),\n'
             '            ("EMA", ema_signal, self.ema.strength),\n'
             '            ("MACD", macd_signal, self.macd.strength),\n'
             '            ("ADX", adx_signal, self.adx.strength),\n        ]')
    s = s.replace(b_old, b_new, 1)
open(p, 'w', encoding='utf-8').write(s)
import py_compile; py_compile.compile(p, doraise=True)
print('patches 3+4 done')