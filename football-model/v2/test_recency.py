"""Nov 23 2026 (Chris: "free agency changes teams every year - why use old seasons?").
Two separate questions, same walk-forward test (game-day line, 2015-22 / 2023-26):
  A. how much of LAST season's team ratings to carry into a new season (now 65%; rest = league average)
  B. how many past seasons the model LEARNS from (now every season since 2009) - it learns what the
     numbers mean (e.g. how much a pass-rush edge is worth), not who is good this year.
    PYTHONPATH=. python v2/test_recency.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl


def wf(d, kind, line, window):
    out = []
    done = d[d.result.notna() & d[line].notna() & (d.season >= 2009)]
    for s in range(2015, int(d.season.max()) + 1):
        tr = done[(done.season < s) & (done.season >= (s - window if window else 0))]
        te = d[(d.season == s) & d[line].notna()].copy()
        te["pred"] = nfl.fit(tr, kind, line).predict(nfl.X(te, te[line], kind)); out.append(te)
    p = pd.concat(out); p = p[p.result.notna()]
    e = p.pred - p[line]; a = (p.result if kind == "spread" else p.total) - p[line]
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=p.index)
    o, n, b = p.season <= 2022, p.season >= 2023, e.abs() >= 1
    f = lambda m: f"{w[m].mean():.1%}"
    return f"all {f(o)} / {f(n)}, edge 1+ {f(o & b)} / {f(n & b)}"


for carry in (0.0, 0.35, 0.5, 0.65):
    nfl.CARRY = carry
    d = nfl.build()
    lab = f"A. carry {carry:.0%} of last season" + ("  (CURRENT)" if carry == 0.65 else "")
    print(f"\n{lab}\n  spread {wf(d, 'spread', 'spread_line', None)}\n  total  {wf(d, 'total', 'total_line', None)}", flush=True)
nfl.CARRY = 0.65
d = nfl.build()
for win in (3, 5, 8):
    print(f"\nB. learn from the last {win} seasons only\n  spread {wf(d, 'spread', 'spread_line', win)}\n  total  {wf(d, 'total', 'total_line', win)}", flush=True)
