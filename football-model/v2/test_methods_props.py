"""Nov 23 2026: props picked WITHOUT averages, vs the current model (fit 2015-22, scored on 2023-26).
  0 current model: chance = how often similar past players reached the number
  1 his own hit rate, last 16 games: e.g. "60+ in 9 of his last 16" (shrunk 4 games toward his position's rate)
  2 his own hit rate, last 8 games
  3 half model, half own last-16 hit rate
Brier score (lower = better) and, where bets are made (chance 60%+), how often they really hit.
    PYTHONPATH=. python v2/test_methods_props.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props
from v2.test_props_new import RUNGS, h

print(f"{'market':16s} {'method':22s} {'Brier':>7s}   chance 60%+: said / hit (n)")
for mk, rungs in RUNGS.items():
    m = props.StatModel(mk)
    x = m.rows(h).sort_values(["player_id", "gameday"])
    m.fit(x[x.season <= 2022])
    te_mask = (x.season >= 2023).values
    pr = m.predict(x[te_mask])
    rows = []
    for r in rungs:
        hit = (x.y >= r).astype(float)
        base = x[x.season <= 2022].groupby("position").apply(lambda q: (q.y >= r).mean())
        g = hit.groupby(x.player_id)
        out = {}
        for n in (16, 8):
            hits = g.transform(lambda s: s.shift().rolling(n, min_periods=1).sum()).fillna(0)
            cnt = g.transform(lambda s: s.shift().rolling(n, min_periods=1).count()).fillna(0)
            b = x.position.map(base).fillna(hit.mean())
            out[n] = ((hits + 4 * b) / (cnt + 4)).values[te_mask]
        pm = np.array([m.p_reach(v, r) for v in pr])
        rows.append(pd.DataFrame({"hit": hit.values[te_mask], "0 model": pm, "1 own last 16": out[16],
                                  "2 own last 8": out[8], "3 half/half": (pm + out[16]) / 2}))
    t = pd.concat(rows)
    for c in ["0 model", "1 own last 16", "2 own last 8", "3 half/half"]:
        hi = t[t[c] >= 0.6]
        print(f"{mk:16s} {c:22s} {((t[c] - t.hit) ** 2).mean():7.4f}   {hi[c].mean():.1%} / {hi.hit.mean():.1%} ({len(hi)})", flush=True)
