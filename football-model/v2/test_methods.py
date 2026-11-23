"""Nov 23 2026 (Chris: "averages skew the picks - find other methods, on all models").
Game model: six ways to choose the spread and total pick, same walk-forward test (fit on earlier
seasons only, graded at the game-day line, 2015-22 / 2023-26, break-even 52.4%).
  0 current: team ratings = weighted averages of recent games; ridge fit on the margin
  1 ratings = MEDIAN of the last 8 games (one blowout moves a median little)
  2 competitive plays only: garbage time (win prob <10% or >90%) removed, each play's EPA capped at +/-3
  3 blowouts capped: the fit counts any miss vs the line as at most 14 points
  4 pick by chance to cover: logistic regression on cover yes/no, no margins at all
  5 similar past games: the 200 most similar earlier games (same inputs) - how often did that side cover?
    PYTHONPATH=. python v2/test_methods.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from v2 import nfl

KINDS = (("spread", "spread_line", "result"), ("total", "total_line", "total"))


def wl(p, edge, kind, line, y):
    a = p[y] - p[line]
    return pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(edge)), index=p.index)


def report(name, res):
    print(f"\n{name}   (2015-22 / 2023-26)")
    for kind, (w, big) in res.items():
        f = lambda m: f"{w[m].mean():.1%} of {int(w[m].notna().sum())}"
        o, n = w.index.isin(w.index), None
        s = SEASON.loc[w.index]
        o, n = s <= 2022, s >= 2023
        print(f"  {kind:6s} all {f(o)} / {f(n)} | confident {f(o & big)} / {f(n & big)}", flush=True)


def ridge_way():
    d = nfl.build()
    res = {}
    for kind, line, y in KINDS:
        p = nfl.walk_forward(d, kind, line); p = p[p.result.notna()]
        e = p.pred - p[line]
        res[kind] = (wl(p, e, kind, line, y), e.abs() >= 1)
    return d, res


def class_way(d, make, label):
    res = {}
    for kind, line, y in KINDS:
        done = d[d.result.notna() & d[line].notna() & (d.season >= 2009)]
        out = []
        for s in range(2015, int(d.season.max()) + 1):
            tr, te = done[done.season < s], done[done.season == s].copy()
            a = tr[y] - tr[line]; tr = tr[a != 0]
            m = make().fit(nfl.X(tr, tr[line], kind), (tr[y] > tr[line]).astype(int))
            te["p"] = m.predict_proba(nfl.X(te, te[line], kind))[:, 1]
            out.append(te)
        p = pd.concat(out)
        e = p.p - 0.5
        res[kind] = (wl(p, e, kind, line, y), e.abs() >= 0.03)
    return res


base = nfl.build()
SEASON = base.season
print("'confident' = edge 1+ pts for 0-3; chance 53%+ or 47%- for 4-5")
_, r = ridge_way(); report("0 CURRENT", r)
nfl.RATING = "median"; _, r = ridge_way(); report("1 ratings = median of last 8 games", r); nfl.RATING = "ewm"
nfl.COMPETITIVE = True; _, r = ridge_way(); report("2 competitive plays only, EPA capped", r); nfl.COMPETITIVE = False
nfl.CLIP = 14; _, r = ridge_way(); report("3 blowouts capped at 14 pts", r); nfl.CLIP = None
report("4 chance to cover (logistic)", class_way(base, lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000)), "logit"))
report("5 200 most similar past games", class_way(base, lambda: make_pipeline(StandardScaler(), KNeighborsClassifier(200)), "knn"))
