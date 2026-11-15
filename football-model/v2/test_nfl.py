"""Walk-forward test of v2: every game gets a pick (no 'no bet'); records by edge size."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl

d = nfl.build()
d.to_pickle(Path(__file__).parent / "nfl_built.pkl")
for kind, fit_on in (("spread", "spread_open"), ("spread", "spread_line"), ("total", "total_open"), ("total", "total_line")):
    p = nfl.walk_forward(d, kind, fit_on)
    p = p[p["result"].notna()]
    line = p[fit_on]
    edge = p["pred"] - line
    actual = (p["result"] if kind == "spread" else p["total"]) - line
    won = np.where(actual == 0, np.nan, np.sign(actual) == np.sign(edge))
    p = p.assign(edge=edge.abs(), won=won)
    print(f"\n{kind} fit+graded vs {fit_on}")
    for lo in (0, 1, 2, 3, 4):
        for per, q in (("2015-22", p[p.season <= 2022]), ("2023-26", p[p.season >= 2023])):
            x = q[q["edge"] >= lo]["won"].dropna()
            print(f"  edge {lo}+ {per}: {x.mean():.1%} of {len(x)}")
