"""Totals Over-bias fix (core/PROTOCOL.md amendment 14). python core/totals_fix.py -> core/results/totals_fix.txt"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb, nfl

txt, res = ['Totals Over-bias fix (amendment 14). Spreads unchanged.'], {}


def college_frame():
    f = cfb.build(4).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    return f


def run(name, mod, frame, bets, early, late):
    txt.append(f'\n===== {name}')
    rows = {}
    for mode in ('ols', 'median', 'offset'):
        mod.TOTAL_MODE = mode
        f = mod.walk_forward(frame)
        r = {}
        for t in (0, 2, 4):
            e, l = bets(f, early, 'total', t), bets(f, late, 'total', t)
            r[t] = (e, l)
        rows[mode] = r
    pick = max(('median', 'offset'), key=lambda m: rows[m][0][0][0] / max(rows[m][0][0][1], 1))
    for mode in ('ols', 'median', 'offset'):
        tag = ' (original)' if mode == 'ols' else ' <- CHOSEN on EARLY' if mode == pick else ''
        txt.append(f'{mode}{tag}:')
        for t in (0, 2, 4):
            e, l = rows[mode][t]
            show_late = mode == 'ols' or mode == pick
            p = cfb.pval(e[0] + l[0], e[1] + l[1])
            ok = e[1] >= 100 and l[1] >= 100 and e[0] / max(e[1], 1) >= .524 and l[0] / max(l[1], 1) >= .524 and p < .05
            late = f"LATE {l[0]}/{l[1]} = {l[0] / max(l[1], 1):.1%} Over share {l[2]:.0%} | p={p:.3f} | {'TESTED PICK' if ok else 'LEAN'}" if show_late else 'LATE not run (not chosen)'
            txt.append(f'  total edge {t}+  EARLY {e[0]}/{e[1]} = {e[0] / max(e[1], 1):.1%} Over share {e[2]:.0%} | {late}')
            res[f'{name}|{mode}|{t}'] = dict(early=e, late=l if show_late else None, p=p if show_late else None, passes=ok if show_late else None)
    lo = rows[pick][0][1][2]
    txt.append(f'Bias fixed (LATE Over share 40-60%)? {"YES" if 0.40 <= lo <= 0.60 else "NO"} ({lo:.0%}) - chosen: {pick}')
    res[f'{name}|chosen'] = pick
    mod.TOTAL_MODE = 'ols'


cfb.EXTRA[:] = cfb.EXTRA_ALL
run('COLLEGE (2017-22 median line / 2023-26 DK)', cfb, college_frame(), cfb.bets, cfb.EARLY, cfb.LATE)
run('NFL (2011-17 / 2018-26)', nfl, nfl.build(4), nfl.bets, nfl.EARLY, nfl.LATE)
open(os.path.join(HERE, 'results', 'totals_fix.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'totals_fix.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
