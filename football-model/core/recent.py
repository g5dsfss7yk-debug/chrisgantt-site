"""Recent-seasons-only fit (core/PROTOCOL.md amendment 16). python core/recent.py -> core/results/recent.txt"""
import os, sys, json, math
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb, nfl

txt, res = ['RECENT-ONLY fit (amendment 16): weights fit on the last 3 seasons, vs the all-seasons fit, same games.'], {}


def college_frame():
    f = cfb.build(4).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    return f


def run(name, mod, frame, P1, P2, total_mode):
    txt.append(f'\n===== {name}  (periods {P1[0]}-{P1[1]} / {P2[0]}-{P2[1]})')
    mod.TOTAL_MODE = total_mode
    fits = {}
    for label, win in (('ALL seasons (current)', None), ('LAST 3 seasons only', 3)):
        mod.WINDOW = win
        f = mod.walk_forward(frame); fits[label] = f
        txt.append(f'{label}:')
        for kind in ('spread', 'total'):
            for t in (0, 2, 4):
                a, b = mod.bets(f, P1, kind, t), mod.bets(f, P2, kind, t)
                p = cfb.pval(a[0] + b[0], a[1] + b[1])
                ok = a[1] >= 100 and b[1] >= 100 and a[0] / max(a[1], 1) >= .524 and b[0] / max(b[1], 1) >= .524 and p < .05
                txt.append(f"  {kind:6s} edge {t}+  {a[0]}/{a[1]} = {a[0] / max(a[1], 1):.1%} | {b[0]}/{b[1]} = {b[0] / max(b[1], 1):.1%} | p={p:.3f} | "
                           f"{'TESTED PICK' if ok else 'LEAN':11s} | {'home' if kind == 'spread' else 'Over'} share {a[2]:.0%} / {b[2]:.0%}")
                res[f'{name}|{label}|{kind}|{t}'] = dict(p1=a[:2], p2=b[:2], p=p, passes=ok)
        we, wl = mod.winner_bets(f, P1), mod.winner_bets(f, P2)
        txt.append(f"  winner 3%+   ROI {we[2].mean():+.1%} ({we[1]}) | ROI {wl[2].mean():+.1%} ({wl[1]})")
    txt.append('  by season (all games), ALL vs LAST-3: spread hit | total hit')
    for y in range(P1[0], P2[1] + 1):
        cells = []
        for label in fits:
            f = fits[label]
            s, t = mod.bets(f, (y, y), 'spread', 0), mod.bets(f, (y, y), 'total', 0)
            cells.append(f'{s[0] / max(s[1], 1):.1%} | {t[0] / max(t[1], 1):.1%}')
        txt.append(f'    {y}: {cells[0]:>16s}   vs   {cells[1]:>16s}')
    mod.WINDOW = None; mod.TOTAL_MODE = 'ols'


cfb.EXTRA[:] = cfb.EXTRA_ALL
run('NFL', nfl, nfl.build(4), (2021, 2023), (2024, 2026), 'ols')
run('COLLEGE', cfb, college_frame(), (2020, 2022), (2023, 2026), 'median')
open(os.path.join(HERE, 'results', 'recent.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'recent.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
