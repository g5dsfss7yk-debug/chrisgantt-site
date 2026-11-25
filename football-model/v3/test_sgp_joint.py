"""How often do same-game ~50% yardage props all hit together? (2023-26, Pricer trained 2013-22).
Each player-game gets the line where the model's Over chance is closest to 50%; then all pairs/triples in the same game."""
import os, sys, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import props

d = props.weekly()
legs = []
for stat in ('receiving_yards', 'rushing_yards'):
    s = props.project(d, stat)
    pr = props.Pricer(s, stat)
    ev = s[(s.season >= 2023) & s.proj.notna() & (s.proj >= 30)]
    for _, r in ev.iterrows():
        best = None
        for m in np.arange(0.5, 1.3, 0.05):
            L = props.half(r.proj * m)
            p = pr.p_over(r.position, r.proj, L)
            if best is None or abs(p - 0.5) < abs(best[1] - 0.5):
                best = (L, p)
        if best and 0.45 <= best[1] <= 0.58:
            legs.append((r.game_id, r.team, stat, r.player_id, best[1], float(r._v > best[0])))
L = pd.DataFrame(legs, columns=['game', 'team', 'stat', 'pid', 'p', 'hit'])
print(f'legs: {len(L)}, single hit rate {L.hit.mean():.1%} (model said {L.p.mean():.1%})')
for k in (2, 3):
    rows = {'same team': [], 'both teams': []}
    for g, x in L.groupby('game'):
        for c in itertools.combinations(x.index, k):
            y = L.loc[list(c)]
            key = 'same team' if y.team.nunique() == 1 else 'both teams'
            rows[key].append((y.hit.prod(), y.p.prod()))
    for key, v in rows.items():
        if v:
            v = np.array(v)
            print(f'{k} legs, {key:10s}: {len(v):6d} combos, all hit {v[:, 0].mean():.1%} (if independent {v[:, 1].mean():.1%})')
