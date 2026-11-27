"""Data audit for college (core/PROTOCOL.md 'audit first'). python core/audit_cfb.py -> core/results/audit_cfb.txt"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data

S = range(2014, 2027)
p = data.cfb_pbp(S); L = data.cfb_lines(S)
out = []
pr = lambda s='': out.append(s)
g = p.groupby('game_id').agg(season=('season', 'first'), week=('week', 'max'), home=('home', 'first'), away=('away', 'first'),
                              hd=('home_team_division', 'first'), ad=('away_team_division', 'first'), plays=('EPA', 'size'))
pr('College data audit (cfbfastR play-by-play, CFBD lines)')
pr(f"{'season':>6} {'games':>6} {'fbs-g':>6} {'plays/g':>8} {'EPA na':>7} {'wp na':>6} {'lines':>6} {'DK':>5} {'DK tot':>6} {'max wk':>6}")
for y in S:
    gy, py, ly = g[g.season == y], p[p.season == y], L[L.season == y]
    fbs = gy[(gy.hd == 'fbs') | (gy.ad == 'fbs')]
    dk = ly[ly.provider == 'DraftKings']
    pr(f"{y:>6} {len(gy):>6} {len(fbs):>6} {gy.plays.mean():>8.0f} {py.EPA.isna().mean():>7.1%} {py.wp_before.isna().mean():>6.1%} "
       f"{ly.game_id.nunique():>6} {dk.spread.notna().sum():>5} {dk.total.notna().sum():>6} {gy.week.max():>6}")
# sign check: home spread vs home margin (expect negative correlation: -7 = home favored by 7)
m = L.dropna(subset=['spread', 'home_score', 'away_score']).groupby('game_id').agg(spread=('spread', 'median'),
                                                                                   hs=('home_score', 'first'), as_=('away_score', 'first'))
c = np.corrcoef(m.spread, m.hs - m.as_)[0, 1]
pr(f"\nSign: corr(CFBD home spread, home margin) = {c:+.3f} (negative = '-7 means home favored', as documented)")
fav = ((m.spread < 0) == (m.hs > m.as_)).mean()
pr(f"Favorite by the line wins {fav:.1%} of {len(m)} games")
d = L.groupby(['game_id', 'provider']).size()
pr(f"Duplicate game/provider line rows: {(d > 1).sum()}")
dup = p.groupby('game_id').season.nunique()
pr(f"Games listed in two seasons: {(dup > 1).sum()}")
# id match: pbp game_id vs CFBD lines game_id
ids = set(g.index.astype(str)); lid = set(L.game_id.astype(str))
pr(f"pbp games with a CFBD line row: {len(ids & lid)} of {len(ids)}; FBS-vs-FBS games 2023-26 with a DK spread: "
   f"{len(set(g[(g.hd=='fbs')&(g.ad=='fbs')&(g.season>=2023)].index.astype(str)) & set(L[(L.provider=='DraftKings')&L.spread.notna()].game_id.astype(str)))}"
   f" of {len(g[(g.hd=='fbs')&(g.ad=='fbs')&(g.season>=2023)])}")
pl = data.cfb_players(S)
pr(f"\nPlayer-game rows: {len(pl)}; seasons {pl.season.min()}-{pl.season.max()}; 2026 max week {pl[pl.season==2026].week.max()}")
os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
open(os.path.join(HERE, 'results', 'audit_cfb.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
