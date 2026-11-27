"""NFL data audit (core/PROTOCOL.md amendment 6). python core/audit_nfl.py -> core/results/audit_nfl.txt"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data

S = range(2006, 2027)
out = []; pr = out.append
g = data.nfl_schedules()
g = g[g.season.between(2006, 2026)]
pb = data.nfl_pbp(S)
pr('NFL data audit (nflverse)')
pr(f"pbp columns missing: {sorted(set(data.NFL_PBP_COLS) - set(pb.columns))}")
pr(f"{'season':>6} {'games':>5} {'final':>5} {'spread':>6} {'sp odds':>7} {'ml':>5} {'outdoor':>7} {'wind na':>7} {'temp na':>7} {'wx text':>7} {'pbp g':>6} {'epa na':>6}")
for y in S:
    x = g[g.season == y]; o = x[x.roof.isin(['outdoors', 'open'])]
    p = pb[pb.season == y]
    pr(f"{y:>6} {len(x):>5} {x.result.notna().sum():>5} {x.spread_line.notna().sum():>6} {x.home_spread_odds.notna().sum():>7} "
       f"{x.home_moneyline.notna().sum():>5} {len(o):>7} {o.wind.isna().mean():>7.0%} {o.temp.isna().mean():>7.0%} "
       f"{o.weather.notna().mean() if 'weather' in o else float('nan'):>7.0%} {p.game_id.nunique():>6} {p.epa.isna().mean():>6.1%}")
f = g.dropna(subset=['spread_line', 'result'])
pr(f"\nSign: corr(spread_line, home margin) = {np.corrcoef(f.spread_line, f.result)[0, 1]:+.3f} "
   "(positive = nflverse spread_line is the HOME team's expected margin; -spread_line is the home number like DK)")
pr(f"result == home_score - away_score: {(f.result == f.home_score - f.away_score).mean():.1%}")
inj = data.nfl_injuries(range(2009, 2027))
pr(f"\nInjury rows by season: {inj.groupby('season').size().astype(int).to_dict()}")
pr(f"Report status: {inj.report_status.value_counts(dropna=False).to_dict()}")
for y in (2009, 2016, 2024, 2025, 2026):
    d = data.nfl_depth(y)
    wk = d.week.nunique() if 'week' in d else d.dt.str[:10].nunique()
    pr(f"Depth chart {y}: {len(d)} rows, {'weeks' if 'week' in d else 'snapshot days'} {wk}, columns {'old' if 'week' in d else 'new (dated snapshots)'}")
rt = pb[pb.return_touchdown == 1] if 'return_touchdown' in pb else pb.iloc[:0]
pr(f"\nReturn TDs flagged: {len(rt)}; on pass/rush plays: {int(((rt['pass'] == 1) | (rt.rush == 1)).sum())}; "
   f"interceptions {int(pb.interception.sum())}, fumbles lost {int(pb.fumble_lost.sum())}")
os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
open(os.path.join(HERE, 'results', 'audit_nfl.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
