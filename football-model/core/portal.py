"""Portal-era ratings test (core/PROTOCOL.md amendment 20). python core/portal.py -> core/results/portal.txt"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb, approaches as A

KS = (1.0, 0.5, 0.25)
txt, res = ['Portal-era ratings (amendment 20): previous-season games weighted k in the college ratings.'], {}
cfb.EXTRA[:] = cfb.EXTRA_ALL
preds = {}
for k in KS:
    cfb.PREV_K = k
    f = cfb.build(4).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    cfb.PREV_K = 1.0
    p = A.base_preds(cfb, f, None, 3, 'median')
    p = A.recalibrate(p, p.home_score - p.away_score, p.home_score + p.away_score)
    preds[k] = p
    x = p[(p.season == 2024) & p.home_score.notna() & p.pm.notna() & p.pt.notna()]
    mse = float(((x.pm - (x.home_score - x.away_score)) ** 2).mean() + ((x.pt - (x.home_score + x.away_score)) ** 2).mean())
    res[f'mse2024|{k}'] = mse
    txt.append(f'k={k}: 2024 squared error margin+total {mse:.1f}')
kc = min(KS, key=lambda k: res[f'mse2024|{k}'])
txt.append(f'Chosen on 2024: k = {kc}. 2025-2026 checked once vs k = 1:\n')
P = (2025, 2026)
for k in sorted({1.0, kc}, reverse=True):
    p = preds[k]
    txt.append(f"k={k}{' (current)' if k == 1.0 else ' (portal-era)'}:")
    for kind in ('spread', 'total'):
        for t in (0, 2):
            w, n, side = cfb.bets(p, cfb.LATE if False else P, kind, t) if False else (None, None, None)
            # graded at DraftKings lines (2023+ rule)
            x = p[p.season.between(*P) & p.home_score.notna() & p.pm.notna()]
            ln = x.spread_dk if kind == 'spread' else x.total_dk
            edge = (x.pm + ln) if kind == 'spread' else (x.pt - ln)
            r = ((x.home_score - x.away_score) + ln) if kind == 'spread' else ((x.home_score + x.away_score) - ln)
            ok = ln.notna() & (edge.abs() >= t) & (r != 0)
            pick = edge > 0; win = np.where(pick, r > 0, r < 0)
            w, n, side = int(win[ok.values].sum()), int(ok.sum()), float(pick[ok].mean())
            res[f'{k}|{kind}|{t}'] = (w, n, side)
            txt.append(f"  {kind:6s} edge {t}+  2025-26: {w}/{n} = {w / max(n, 1):.1%} | {'home' if kind == 'spread' else 'Over'} share {side:.0%}")
    y = [(s, preds[k][(preds[k].season == s) & preds[k].home_score.notna()]) for s in P]
sw = lambda k, kind: res[f'{k}|{kind}|0'][0] / max(res[f'{k}|{kind}|0'][1], 1)
switch = kc != 1.0 and sw(kc, 'spread') > sw(1.0, 'spread') and sw(kc, 'total') > sw(1.0, 'total')
txt.append(f"\nCard switches to k = {kc}? {'YES' if switch else 'NO'} (needs better spread AND total all-games hit rate in 2025-26 than k = 1)")
res['chosen'] = kc; res['switch'] = switch
open(os.path.join(HERE, 'results', 'portal.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'portal.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
