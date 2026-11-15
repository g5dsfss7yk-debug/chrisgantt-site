"""Alternate spreads/totals from v2: chance from past residuals (actual - model). Fit residuals
on 2015-22, test 2023-26 calibration over a grid of alternate numbers."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl
d = nfl.build()
for kind, col, y in (("spread", "spread_open", "result"), ("total", "total_line", "total")):
    p = nfl.walk_forward(d, kind, col); p = p[p[y].notna()]
    res = (p[y] - p.pred).values
    old, new = p.season <= 2022, p.season >= 2023
    r_old = np.sort(res[old.values])
    rows = []
    for alt in np.arange(-14, 14.5, 1.0):     # threshold relative to the model's number
        q = p[new]
        thr = q.pred + alt
        prob = 1 - np.searchsorted(r_old, alt, side="right") / len(r_old)
        rows.append(pd.DataFrame({"p": prob, "hit": (q[y] > thr).values}))
    t = pd.concat(rows)
    b = pd.cut(t.p, [0, .2, .4, .5, .6, .7, .8, .9, 1])
    print(kind, "\n", t.groupby(b, observed=True).agg(n=("hit", "size"), model=("p", "mean"), hit=("hit", "mean")).round(3).to_string())
    import json
    CAL = Path(__file__).parent / "calib.json"
    cal = json.load(open(CAL)) if CAL.exists() else {}
    e = np.round(np.arange(0, 1.0001, 0.05), 2)
    cc = t.groupby(pd.cut(t.p, e), observed=False)["hit"].agg(["mean", "size"])
    cal["alt " + kind] = {"edges": e.tolist(), "hit": [None if n < 30 else float(m) for m, n in zip(cc["mean"], cc["size"])], "n": cc["size"].astype(int).tolist()}
    json.dump(cal, open(CAL, "w"))
    np.save(Path(__file__).parent / f"resid_{kind}.npy", np.sort(res))
