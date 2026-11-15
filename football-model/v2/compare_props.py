"""Old vs new props inputs (opponent defense + long-run star level), fit 2015-22, scored 2023-26.
Lower error = more accurate. Brier = squared error of ladder chances (rungs as in test_props)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props
s = props.history(props.load()); s = s[s.season >= 2015]
RUNGS = {"rushing_yards": [25, 40, 60, 80, 100], "receiving_yards": [25, 40, 60, 80, 100], "passing_yards": [200, 225, 250, 275, 300],
         "receptions": [3, 4, 5, 6, 7], "rush_rec_yards": [50, 75, 100, 125], "passing_tds": [1, 2, 3], "anytime_td": [1]}
for mk, rungs in RUNGS.items():
    res = {}
    for new in (False, True):
        props.USE_NEW = new
        m = props.StatModel(mk); x = m.rows(s); m.fit(x[x.season <= 2022]); te = x[x.season >= 2023]
        pr = m.predict(te)
        top = pr >= np.quantile(pr, 0.9)
        br, brt = [], []
        for r in rungs:
            p = np.array([m.p_reach(v, r) for v in pr]); h = te["y"].values >= r
            br.append((p - h) ** 2); brt.append(((p - h) ** 2)[top])
        mae = np.abs(pr - te["y"].values).mean() if mk != "anytime_td" else np.nan
        res[new] = (np.concatenate(br).mean(), np.concatenate(brt).mean(), mae)
    o, n = res[False], res[True]
    print(f"{mk:16s} Brier all {o[0]:.4f} -> {n[0]:.4f} ({(n[0]/o[0]-1):+.1%}) | top-10% players {o[1]:.4f} -> {n[1]:.4f} ({(n[1]/o[1]-1):+.1%}) | MAE {o[2]:.2f} -> {n[2]:.2f}", flush=True)
