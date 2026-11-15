"""Fit v2 props on 2015-2022, test 2023-26: does 'model says X%' hit X%?"""
import sys, pickle, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props
s = props.history(props.load())
s = s[s.season >= 2015]
ONLY = sys.argv[1:]
CAL = Path(__file__).parent / 'calib.json'
RUNGS = {"rushing_yards": [25, 40, 50, 60, 75, 100], "receiving_yards": [25, 40, 50, 60, 75, 100],
         "passing_yards": [175, 200, 225, 250, 275, 300], "receptions": [2, 3, 4, 5, 6, 7],
         "rush_rec_yards": [40, 60, 75, 100, 125], "passing_tds": [1, 2, 3], "anytime_td": [1]}
for mk, rungs in RUNGS.items():
    if ONLY and mk not in ONLY: continue
    m = props.StatModel(mk)
    x = m.rows(s)
    m.fit(x[x.season <= 2022])
    te = x[x.season >= 2023]
    pr = m.predict(te)
    rows = []
    for r in rungs:
        p = np.array([m.p_reach(v, r) for v in pr])
        rows.append(pd.DataFrame({"p": p, "hit": te["y"].values >= r, "top": pr >= np.quantile(pr, 0.95)}))
    t = pd.concat(rows)
    b = pd.cut(t.p, [0, .2, .4, .5, .6, .7, .8, .9, 1.0])
    c = t.groupby(b, observed=True).agg(n=("hit", "size"), model=("p", "mean"), hit=("hit", "mean"))
    print(f"\n{mk} (2023-26, model fit through 2022)\n{c.round(3).to_string()}", flush=True)
    cal = json.load(open(CAL)) if CAL.exists() else {}
    e = np.round(np.arange(0, 1.0001, 0.05), 2)
    cc = t.groupby(pd.cut(t.p, e), observed=False)["hit"].agg(["mean", "size"])
    cal[mk] = {"edges": e.tolist(), "hit": [None if n < 30 else float(m) for m, n in zip(cc["mean"], cc["size"])],
               "n": cc["size"].astype(int).tolist()}
    json.dump(cal, open(CAL, "w"))
    tt = t[t.top]
    c2 = tt.groupby(pd.cut(tt.p, [0, .2, .4, .5, .6, .7, .8, .9, 1.0]), observed=True).agg(n=("hit", "size"), model=("p", "mean"), hit=("hit", "mean"))
    print(f"  stars only (top 5% projections):\n{c2.round(3).to_string()}", flush=True)
