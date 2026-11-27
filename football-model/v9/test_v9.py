"""v9 weather severity test, rules in v9/PROTOCOL.md (committed first). python v9/test_v9.py"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
for p in ('v3', 'v6', 'v7'):
    sys.path.insert(0, os.path.join(ROOT, p))
import props
import test_v7 as v7, test_weather as v6

LEVELS = {
    'WET1': lambda w: w.rain >= 0.10,
    'HEAVY': lambda w: w.rain >= 0.30,
    'COLDWET': lambda w: (w.rain >= 0.10) & (w.temp <= 36),
    'GUST30': lambda w: w.gust >= 30,
}


if __name__ == '__main__':
    W = pd.read_csv(os.path.join(ROOT, 'data', 'v9', 'game_weather.csv'))
    bad6 = v6.weather()[['game_id', 'bad']]
    W = W.merge(bad6, on='game_id', how='left')
    W['bad'] = W.bad.fillna(False).astype(bool)
    for k, f in LEVELS.items():
        W[k] = f(W)
    g = v7.games()
    G = g.merge(W, on=['game_id', 'season'])
    R, lines = {}, [f"Games with game-window weather: {len(W)}; " + ', '.join(f'{k} {int(W[k].sum())}' for k in LEVELS) + f", v6 BAD {int(W.bad.sum())}"]
    lines.append('\nTOTALS - UNDER at the closing total, -110 (needs 52.4% both periods, 100+ each)')
    for key, lev in (('S1', 'WET1'), ('S2', 'HEAVY'), ('S3', 'COLDWET'), ('S4', 'GUST30'), ('ref', 'bad')):
        x = G[G[lev]].reset_index(drop=True)
        r = v7.game_result(x, x.total < x.total_line, x.total == x.total_line, (2006, 2016), (2017, 2026))
        name = f'{key} total UNDER, {lev}' if key != 'ref' else 'ref total UNDER, all v6-BAD games'
        if key != 'ref':
            R[name] = r
        lines.append(f"  {name:36s} EARLY {r['early'][0]}/{r['early'][1]} = {r['early_pct']:.1%} | LATE {r['late'][0]}/{r['late'][1]} = {r['late_pct']:.1%} | "
                     f"p={r['p']:.3f} | {'PASS' if r['passes'] else 'FAIL' if key != 'ref' else 'reference'}")
    d = props.weekly()
    wl = W.set_index('game_id')
    tests = [('S5', 'passing_yards', 'under', 'HEAVY'), ('S6', 'receiving_yards', 'under', 'HEAVY'), ('S7', 'receptions', 'under', 'HEAVY'),
             ('S8', 'rushing_yards', 'over', 'HEAVY'), ('S9', 'passing_yards', 'under', 'COLDWET'), ('S10', 'receptions', 'under', 'COLDWET'),
             ('S11', 'passing_yards', 'under', 'GUST30'), ('S12', 'receptions', 'under', 'GUST30')]
    lines.append('\nPROPS - line = v3 projection; actual vs v3 chance for that side (needs +3.0 pts both periods, 100+ each)')
    for key, stat, side, lev in tests:
        e = v7.evals(d, stat).join(wl[[lev, 'bad']], on='game_id')
        r = v7.prop_result(e[e[lev] == True], side); ref = v7.prop_result(e[e.bad == True], side)
        name = f'{key} {stat} {side.upper()}, {lev}'
        R[name] = r
        lines.append(f"  {name:36s} 2019-22 n={r['early']['n']:5d} {r['early']['actual']:.1%} vs {r['early']['predicted']:.1%} ({r['gap_early']*100:+.1f}) | "
                     f"2023-26 n={r['late']['n']:5d} {r['late']['actual']:.1%} vs {r['late']['predicted']:.1%} ({r['gap_late']*100:+.1f}) | p={r['p']:.3f} | "
                     f"{'PASS' if r['passes'] else 'FAIL'}   [all v6-BAD: {ref['gap_early']*100:+.1f} / {ref['gap_late']*100:+.1f}]")
    txt = '\n'.join(lines); print(txt)
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    open(os.path.join(HERE, 'results', 'v9_test.txt'), 'w').write('v9 weather severity test (v9/PROTOCOL.md)\n' + txt + '\n')
    json.dump(R, open(os.path.join(HERE, 'results', 'v9_test.json'), 'w'), indent=1, default=float)
