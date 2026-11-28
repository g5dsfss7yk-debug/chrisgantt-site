"""Centered spreads (core/PROTOCOL.md amendment 26). python core/balance_spread.py -> core/results/balance_spread.txt"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb, nfl, approaches as A

txt, res = ['Centered spreads (amendment 26): R rolling median, S same-week median of the spread edge.'], {}


def college():
    f = cfb.build(4).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    p = A.base_preds(cfb, f, None, 3, 'median')
    p = A.recalibrate(p, p.home_score - p.away_score, p.home_score + p.away_score)
    p['margin'] = p.home_score - p.away_score
    ln = np.where(p.season >= 2023, p.spread_dk, p.spread_med)      # home number (-7 = home favored)
    p['edge'] = p.pm + ln; p['res'] = p.margin + ln; p['wk'] = p.week; p['dt'] = p.date
    return p


def pro():
    p = A.base_preds(nfl, nfl.build(4), None, None, 'ols')
    p['edge'] = p.pm - p.spread_line; p['res'] = p.result - p.spread_line; p['wk'] = p.week; p['dt'] = p.gameday
    return p


def run(name, p, N, P):
    p = p.sort_values('dt').reset_index(drop=True)
    key = (p.season * 100 + p.wk.fillna(0)).values; e = p.edge.values
    cen = np.full(len(p), np.nan)
    for k in np.unique(key):
        idx = np.where(key == k)[0]; prev = e[:idx.min()]; prev = prev[~np.isnan(prev)][-N:]
        if len(prev) >= N // 2:
            cen[idx] = np.median(prev)
    p['R'] = p.edge - cen
    p['S'] = p.edge - p.edge.groupby(key).transform('median')
    txt.append(f'\n===== {name}')
    for lab, col in (('CURRENT', 'edge'), ('R rolling', 'R'), ('S slate', 'S')):
        txt.append(f'{lab}:')
        for t in (0, 2, 4):
            out = []
            for per in P:
                m = p.season.between(*per) & p[col].notna() & p.res.notna() & (p.res != 0) & (p[col].abs() >= t)
                home = p[col][m] > 0; win = np.where(home, p.res[m] > 0, p.res[m] < 0)
                out.append((int(win.sum()), int(m.sum()), float(home.mean()) if m.any() else float('nan')))
            pv = cfb.pval(out[0][0] + out[1][0], out[0][1] + out[1][1])
            ok = all(o[1] >= 100 and o[0] / o[1] >= .524 for o in out) and pv < .05
            txt.append(f"  spread edge {t}+  {out[0][0]}/{out[0][1]} = {out[0][0] / max(out[0][1], 1):.1%} home {out[0][2]:.0%} | "
                       f"{out[1][0]}/{out[1][1]} = {out[1][0] / max(out[1][1], 1):.1%} home {out[1][2]:.0%} | p={pv:.3f} | {'TESTED PICK' if ok else 'LEAN'}")
            res[f'{name}|{lab}|{t}'] = dict(p1=out[0][:2], p2=out[1][:2], home=[out[0][2], out[1][2]], p=pv, passes=ok)
        m = p.season.between(P[0][0], P[1][1]) & p[col].notna() & (p.res != 0) & p.res.notna()
        l9 = m & (p.wk >= 9)
        h9 = float((p[col][l9] > 0).mean()); w9 = float(np.where(p[col][l9] > 0, p.res[l9] > 0, p.res[l9] < 0).mean())
        txt.append(f'  weeks 9+: home {h9:.0%}, hit {w9:.1%}')
        res[f'{name}|{lab}|wk9'] = dict(home=h9, hit=w9)
        by = []
        for y in range(P[0][0], P[1][1] + 1):
            s = m & (p.season == y)
            if s.any():
                by.append(f"{y}: {(p[col][s] > 0).mean():.0%} H / {np.where(p[col][s] > 0, p.res[s] > 0, p.res[s] < 0).mean():.1%}")
        txt.append('  by season (home share / hit): ' + ' | '.join(by))
    cur = res[f'{name}|CURRENT|0']; rate = lambda r, k: r[k][0] / max(r[k][1], 1)
    qual = {}
    for lab in ('R rolling', 'S slate'):
        r = res[f'{name}|{lab}|0']
        qual[lab] = all(0.40 <= h <= 0.60 for h in r['home']) and 0.40 <= res[f'{name}|{lab}|wk9']['home'] <= 0.60 and \
            all(rate(r, k) >= rate(cur, k) for k in ('p1', 'p2'))
    ok = [l for l in qual if qual[l]]
    win = max(ok, key=lambda l: res[f'{name}|{l}|0']['p1'][0] + res[f'{name}|{l}|0']['p2'][0]) if ok else None
    txt.append(f"Qualifies: {', '.join(ok) or 'none'} -> card uses: {win or 'CURRENT (no version qualified)'}")
    res[f'{name}|winner'] = win


cfb.EXTRA[:] = cfb.EXTRA_ALL
run('COLLEGE (2020-22 / 2023-26 DK)', college(), 400, ((2020, 2022), (2023, 2026)))
run('NFL (2021-23 / 2024-26)', pro(), 100, ((2021, 2023), (2024, 2026)))
open(os.path.join(HERE, 'results', 'balance_spread.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'balance_spread.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
