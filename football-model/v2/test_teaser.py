"""v2 picks as 6-point teaser legs and moneyline/parlay legs, graded vs the closing line."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl
d = nfl.build()
p = nfl.walk_forward(d, "spread", "spread_open")
p = p[p.result.notna() & p.spread_line.notna()]
pick_home = p.pred > p.spread_open
line = p.spread_line                                   # bet at close
pick_line = np.where(pick_home, -line, line)           # points the pick gets (+ = dog)
margin = np.where(pick_home, p.result, -p.result)      # pick's margin
p = p.assign(pick_line=pick_line, margin=margin, edge=(p.pred - p.spread_open).abs())
p["tease_won"] = (p.margin + p.pick_line + 6) > 0
p["su_won"] = p.margin > 0
b = pd.cut(p.pick_line, [-30, -7.5, -3.5, -1, 0.5, 2.5, 3.5, 6.5, 30],
           labels=["fav 8+", "fav 4-7.5", "fav 1.5-3", "pk/-1", "dog 1-2.5", "dog 3-3.5", "dog 4-6.5", "dog 7+"])
for per, q in (("2015-22", p.season <= 2022), ("2023-26", p.season >= 2023)):
    t = p[q].groupby(b[q], observed=True).agg(n=("tease_won", "size"), teaser_leg=("tease_won", "mean"), straight_up=("su_won", "mean"))
    print(per, "\n", t.round(3).to_string())
