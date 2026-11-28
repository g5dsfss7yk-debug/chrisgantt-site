"""Centered totals (core/PROTOCOL.md amendment 22). python core/balance.py -> core/results/balance.txt"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb, nfl

txt, res = ['Centered totals (amendment 22): edge = (model - line) - median(model - line) over the previous N games.'], {}


def college_frame():
    f = cfb.build(4).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    return f


def preds(mod, f, window, mode, first):
    f = f.copy(); f['pt'] = np.nan
    for S in range(first + 1, 2027):
        a = first if window is None else max(first, S - window)
        mod.TOTAL_MODE = mode
        bt, _ = mod.fit(f[f.season.between(a, S - 1)], 'total')
        te = f.season == S
        f.loc[te, 'pt'] = mod.design(f[te], 'total').values @ bt.values
    mod.TOTAL_MODE = 'ols'
    return f


def run(name, f, N, P, line_early, line_late, total_col, wk_col, date_col):
    f = f.sort_values([date_col]).reset_index(drop=True)
    seasons = f.season.values
    ln = np.where(f.season.between(*P[1]), f[line_late], f[line_early]) if line_late != line_early else f[line_early].values
    f['ln'] = ln
    raw = f.pt - f.ln
    # median of previous N games' (model - line), using only games in earlier weeks (no same-week look-ahead)
    key = f.season * 100 + f[wk_col].fillna(0)
    cen = np.full(len(f), np.nan)
    vals = raw.values; keys = key.values
    for k in np.unique(keys):
        idx = np.where(keys == k)[0]; first = idx.min()
        prev = vals[:first][~np.isnan(vals[:first])][-N:]
        if len(prev) >= N // 2:
            cen[idx] = np.median(prev)
    f['edge_raw'] = raw; f['edge_c'] = raw - cen
    res_ = f[total_col] - f.ln
    txt.append(f'\n===== {name}')
    for lab, col in (('CURRENT (raw edge)', 'edge_raw'), ('CENTERED', 'edge_c')):
        txt.append(f'{lab}:')
        for t in (0, 2, 4):
            out = []
            for per in P:
                m = f.season.between(*per) & f[col].notna() & f.ln.notna() & res_.notna() & (res_ != 0) & (f[col].abs() >= t)
                over = f[col][m] > 0; win = np.where(over, res_[m] > 0, res_[m] < 0)
                out.append((int(win.sum()), int(m.sum()), float(over.mean()) if m.any() else float('nan')))
            p = cfb.pval(out[0][0] + out[1][0], out[0][1] + out[1][1])
            ok = all(o[1] >= 100 and o[0] / o[1] >= .524 for o in out) and p < .05
            txt.append(f"  total edge {t}+  {out[0][0]}/{out[0][1]} = {out[0][0] / max(out[0][1], 1):.1%} Overs {out[0][2]:.0%} | "
                       f"{out[1][0]}/{out[1][1]} = {out[1][0] / max(out[1][1], 1):.1%} Overs {out[1][2]:.0%} | p={p:.3f} | {'TESTED PICK' if ok else 'LEAN'}")
            res[f'{name}|{lab}|{t}'] = dict(p1=out[0][:2], p2=out[1][:2], over=[out[0][2], out[1][2]], p=p, passes=ok)
        m = f.season.between(P[0][0], P[1][1]) & f[col].notna() & f.ln.notna() & (res_ != 0)
        late = m & (f[wk_col] >= 9)
        o9 = float((f[col][late] > 0).mean()); w9 = float(np.where(f[col][late] > 0, res_[late] > 0, res_[late] < 0).mean())
        txt.append(f'  weeks 9+: Overs {o9:.0%}, hit {w9:.1%} ({int(late.sum())} games)')
        res[f'{name}|{lab}|wk9'] = dict(over=o9, hit=w9)
        by = []
        for y in range(P[0][0], P[1][1] + 1):
            s = m & (f.season == y)
            if s.any():
                by.append(f"{y}: {(f[col][s] > 0).mean():.0%} O / {np.where(f[col][s] > 0, res_[s] > 0, res_[s] < 0).mean():.1%}")
        txt.append('  by season (Over share / hit): ' + ' | '.join(by))
    c, r = res[f'{name}|CENTERED|0'], res[f'{name}|CURRENT (raw edge)|0']
    fixed = all(0.40 <= o <= 0.60 for o in c['over']) and 0.40 <= res[f'{name}|CENTERED|wk9']['over'] <= 0.60 and \
        all(c[k][0] / c[k][1] >= r[k][0] / r[k][1] for k in ('p1', 'p2'))
    txt.append(f"FIXED by the rule (40-60% Overs both periods and weeks 9+, all-games hit not lower)? {'YES' if fixed else 'NO'}")
    res[f'{name}|fixed'] = fixed


cfb.EXTRA[:] = cfb.EXTRA_ALL
fc = preds(cfb, college_frame(), 3, 'median', cfb.FIRST)
fc['total'] = fc.home_score + fc.away_score
run('COLLEGE (2020-22 median line / 2023-26 DK)', fc, 400, ((2020, 2022), (2023, 2026)), 'total_med', 'total_dk', 'total', 'week', 'date')
fn = preds(nfl, nfl.build(4), None, 'ols', nfl.FIRST_FIT)
run('NFL (2021-23 / 2024-26)', fn, 100, ((2021, 2023), (2024, 2026)), 'total_line', 'total_line', 'total', 'week', 'gameday')
open(os.path.join(HERE, 'results', 'balance.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'balance.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
