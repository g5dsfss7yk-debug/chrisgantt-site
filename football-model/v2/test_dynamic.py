"""Nov 23 2026 (Chris: "make it dynamic and self-improve from its mistakes"). Two ways a model can
learn from its own misses, tested walk-forward (game-day line, 2015-22 / 2023-26):
  A. recent seasons count more in the fit (half-life 2 or 4 seasons) instead of all seasons equally
  B. correct each pick by the model's own average miss over its last N games this season and last
     (it learns, week by week, which way it has been wrong)
    PYTHONPATH=. python v2/test_dynamic.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from v2 import nfl

d = nfl.build()
done_all = d[d.result.notna() & (d.season >= 2009)]


def run(kind, line, y, hl=None, fix_n=None):
    done = done_all[done_all[line].notna()]
    out = []
    for s in range(2015, int(d.season.max()) + 1):
        tr = done[done.season < s]
        te = done[done.season == s].copy()
        yy = tr[y]
        w = None if hl is None else 0.5 ** ((s - 1 - tr.season) / hl)
        m = make_pipeline(StandardScaler(), Ridge(alpha=nfl.ALPHA[kind]))
        m.fit(nfl.X(tr, tr[line], kind), yy, ridge__sample_weight=w)
        te["pred"] = m.predict(nfl.X(te, te[line], kind))
        out.append(te)
    p = pd.concat(out).sort_values(["gameday", "gametime"])
    if fix_n:   # subtract the model's own average miss over its previous fix_n graded games
        miss = (p.pred - p[y])
        p["pred"] = p.pred - miss.shift(1).rolling(fix_n, min_periods=50).mean().fillna(0)
    e = p.pred - p[line]; a = p[y] - p[line]
    wl = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=p.index)
    o, n, b = p.season <= 2022, p.season >= 2023, e.abs() >= 1
    f = lambda m: f"{wl[m].mean():.1%}"
    return f"all {f(o)} / {f(n)}, edge 1+ {f(o & b)} / {f(n & b)}"


for name, kw in (("CURRENT (all seasons equal)", {}), ("A. recent seasons weighted, half-life 4", {"hl": 4}),
                 ("A. recent seasons weighted, half-life 2", {"hl": 2}),
                 ("B. correct by own miss, last 100 games", {"fix_n": 100}), ("B. correct by own miss, last 250 games", {"fix_n": 250})):
    print(f"\n{name}   (2015-22 / 2023-26)")
    print("  spread", run("spread", "spread_line", "result", **kw))
    print("  total ", run("total", "total_line", "total", **kw), flush=True)
