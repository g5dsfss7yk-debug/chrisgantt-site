"""Nov 23 2026: after adding weather, passing props in rain/snow or 15+ mph wind were still rated too
high. Correction = how far off the model was in those games in 2020-22 (model fit on 2015-19 only);
then checked on 2023-26 with the model fit on 2015-22.
    PYTHONPATH=. python v2/test_wx_fix.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props
from v2.test_props_weather import RUNGS, h

props.USE_WX = True
bad = (h.wx_rain >= 0.5) | (h.wx_snow >= 0.5) | (h.wx_wind >= 15)
out = {}
for mk in ("passing_yards", "passing_tds", "receiving_yards", "receptions", "rush_rec_yards", "anytime_td"):
    rungs = RUNGS[mk]
    def run(train, test):
        m = props.StatModel(mk); x = m.rows(h); m.fit(x[train(x.season)])
        te = x[test(x.season)]; pr = m.predict(te)
        return pd.concat([pd.DataFrame({"p": [m.p_reach(v, r) for v in pr], "hit": (te.y.values >= r).astype(float),
                                        "bad": bad.loc[te.index].values}) for r in rungs])
    a = run(lambda s: s <= 2019, lambda s: s.between(2020, 2022))
    fix = a[a.bad].hit.mean() - a[a.bad].p.mean()          # measured 2020-22
    b = run(lambda s: s <= 2022, lambda s: s >= 2023)
    bb = b[b.bad]
    pf = (bb.p + fix).clip(0.001, 0.999)
    out[mk] = fix
    print(f"{mk:16s} fix {fix:+.1%} (from 2020-22, {int(a.bad.sum())} rungs) | 2023-26 bad weather ({len(bb)} rungs): "
          f"real minus model {bb.hit.mean() - bb.p.mean():+.1%} -> {bb.hit.mean() - pf.mean():+.1%}; "
          f"Brier {((bb.p - bb.hit) ** 2).mean():.4f} -> {((pf - bb.hit) ** 2).mean():.4f}", flush=True)
print("FIX =", {k: round(v, 3) for k, v in out.items()})
