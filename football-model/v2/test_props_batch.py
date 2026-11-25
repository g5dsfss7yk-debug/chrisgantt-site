"""Nov 23 2026 batch: props variables not yet tested, each added alone to the current props model.
Fit 2015-22, scored on 2023-26. Brier score per market (lower = better); kept only if it helps.
  red-zone / goal-line touches and shares | depth of target + QB completion % over expected |
  receiver separation (Next Gen Stats) | artificial turf
    PYTHONPATH=. python v2/test_props_batch.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props
from v2.test_props_weather import RUNGS

for f in ("USE_RZ", "USE_ADOT", "USE_SEP", "USE_TURF"):
    setattr(props, f, True)                      # load every column once
s = props.load().query("season >= 2015")
h = props.history(s)
TESTS = [("CURRENT", []), ("red-zone / goal-line", ["USE_RZ"]), ("depth of target + CPOE", ["USE_ADOT"]),
         ("separation", ["USE_SEP"]), ("turf", ["USE_TURF"])]
ONLY = sys.argv[1:]
res = {}
for name, on in TESTS:
    if ONLY and name != "CURRENT" and not any(o in name for o in ONLY):
        continue
    for f in ("USE_RZ", "USE_ADOT", "USE_SEP", "USE_TURF"):
        setattr(props, f, f in on)
    line = []
    for mk, rungs in RUNGS.items():
        m = props.StatModel(mk); x = m.rows(h); m.fit(x[x.season <= 2022])
        te = x[x.season >= 2023]; pr = m.predict(te)
        p = np.concatenate([[m.p_reach(v, r) for v in pr] for r in rungs])
        y = np.concatenate([(te.y.values >= r).astype(float) for r in rungs])
        res[(name, mk)] = ((p - y) ** 2).mean()
        line.append(f"{mk} {res[(name, mk)]:.4f}" + ("" if name == "CURRENT" else f" ({res[(name, mk)] - res[('CURRENT', mk)]:+.4f})"))
    print(f"{name:24s} " + "  ".join(line), flush=True)
