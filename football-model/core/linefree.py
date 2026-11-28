"""Line-free game models, college and NFL (core/PROTOCOL.md amendment 12). python core/linefree.py -> core/results/linefree.txt"""
import os, sys, json, math
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb, nfl

THR = (0, 2, 4, 7)
txt, res = ['LINE-FREE game models (amendment 12): no betting line in the model; bets graded at the line.'], {}


def college_frame(H):
    f = cfb.build(H).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    return f


def run(name, mod, frame, bets, winner, early, late, Hs, y_margin, y_total):
    txt.append(f'\n===== {name}')
    mse = {}
    mod.LINE_FREE = True
    for H in Hs:
        f = mod.walk_forward(frame(H))
        e = f[f.season.between(*early) & f.pm.notna() & y_margin(f).notna()]
        mse[H] = float(((e.pm - y_margin(e)) ** 2).mean() + ((e.pt - y_total(e)) ** 2).mean())
        txt.append(f'H={H:2d}: EARLY squared error margin+total {mse[H]:.1f}')
    H = min(mse, key=mse.get); txt.append(f'Chosen on EARLY: H = {H}')
    out = {}
    for lf in (True, False):
        mod.LINE_FREE = lf
        f = mod.walk_forward(frame(H))
        e = f[f.season.between(*early) & f.pm.notna() & y_margin(f).notna()]
        txt.append(f"\n{'LINE-FREE' if lf else 'with the line (as before)'}: EARLY squared error margin {((e.pm - y_margin(e)) ** 2).mean():.1f}, total {((e.pt - y_total(e)) ** 2).mean():.1f}")
        for kind in ('spread', 'total'):
            for t in THR:
                a, b = bets(f, early, kind, t)[:2], bets(f, late, kind, t)[:2]
                p = cfb.pval(a[0] + b[0], a[1] + b[1])
                ok = a[1] >= 100 and b[1] >= 100 and a[0] / max(a[1], 1) >= .524 and b[0] / max(b[1], 1) >= .524 and p < .05
                side = bets(f, late, kind, t)[2]
                txt.append(f"  {kind:6s} edge {t}+  EARLY {a[0]}/{a[1]} = {a[0] / max(a[1], 1):.1%} | LATE {b[0]}/{b[1]} = {b[0] / max(b[1], 1):.1%} | p={p:.3f} | "
                           f"{'TESTED PICK' if ok else 'LEAN':11s} | {'home' if kind == 'spread' else 'Over'} share LATE {side:.0%}")
                if lf:
                    out[f'{kind} edge {t}+'] = dict(early=a, late=b, p=p, passes=ok)
        we, wl = winner(f, early), winner(f, late); allp = np.concatenate([we[2], wl[2]])
        tt = allp.mean() / (allp.std(ddof=1) / math.sqrt(len(allp))) if len(allp) > 2 else 0
        pw = 0.5 * math.erfc(tt / math.sqrt(2))
        okw = we[1] >= 100 and wl[1] >= 100 and we[2].mean() > 0 and wl[2].mean() > 0 and pw < .05
        txt.append(f"  winner 3%+   EARLY {we[0]}/{we[1]} ROI {we[2].mean():+.1%} | LATE {wl[0]}/{wl[1]} ROI {wl[2].mean():+.1%} | p={pw:.3f} | {'TESTED PICK' if okw else 'LEAN'}")
        if lf:
            out['winner 3%+'] = dict(early=[we[0], we[1]], late=[wl[0], wl[1]], roi=[float(we[2].mean()), float(wl[2].mean())], p=pw, passes=okw)
    mod.LINE_FREE = False
    res[name] = dict(H=H, mse=mse, results=out)


cfb.EXTRA[:] = cfb.EXTRA_ALL
run('COLLEGE (2017-22 median line / 2023-26 DraftKings)', cfb, college_frame, cfb.bets, cfb.winner_bets, cfb.EARLY, cfb.LATE, cfb.H_GRID,
    lambda f: f.home_score - f.away_score, lambda f: f.home_score + f.away_score)
run('NFL (2011-17 / 2018-26 closing lines)', nfl, nfl.build, nfl.bets, nfl.winner_bets, nfl.EARLY, nfl.LATE, nfl.H_GRID,
    lambda f: f.result, lambda f: f.total)
os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
open(os.path.join(HERE, 'results', 'linefree.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'linefree.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
