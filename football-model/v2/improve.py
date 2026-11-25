"""Nov 15 2026 check of three fixes: wind filled in, features standardized, ridge strength.
Ridge strength is picked on 2015-22 only; 2023-26 is the check. Graded the way Chris bets:
pick vs the game-day (closing) line.     PYTHONPATH=. python v2/improve.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl

d = nfl.build()
d.to_pickle(Path(__file__).parent / "nfl_built.pkl")


def rec(w, m):
    w = w[m].dropna()
    return f"{w.mean():.1%} of {len(w)}"


def spread(fit_col):
    p = nfl.walk_forward(d, "spread", fit_col)
    p = p[p.result.notna() & p.spread_line.notna()]
    e = p.pred - p.spread_line
    a = p.result - p.spread_line
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=p.index)
    o, n = p.season <= 2022, p.season >= 2023
    big = e.abs() >= 1
    return f"all {rec(w, o)} / {rec(w, n)} | edge 1+ {rec(w, o & big)} / {rec(w, n & big)}"


def total():
    p = nfl.walk_forward(d, "total", "total_line")
    p = p[p.result.notna()]
    e = p.pred - p.total_line
    a = p.total - p.total_line
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=p.index)
    o, n = p.season <= 2022, p.season >= 2023
    big = e.abs() >= 1
    return (f"all {rec(w, o)} / {rec(w, n)} | edge 1+ {rec(w, o & big)} / {rec(w, n & big)} | "
            f"Over picks {(e[o] > 0).mean():.0%} / {(e[n] > 0).mean():.0%}, 2026 {(e[p.season == 2026] > 0).mean():.0%}")


for scale in (False, True):
    for alpha in ((30,) if not scale else (10, 30, 100, 300, 1000, 3000)):
        nfl.SCALE, nfl.ALPHA = scale, {"spread": alpha, "total": alpha}
        print(f"\nscaled={scale} alpha={alpha}   (2015-22 / 2023-26)")
        print("  spread, fit on opener (card):", spread("spread_open"))
        print("  spread, fit on game-day line:", spread("spread_line"))
        print("  total:", total(), flush=True)
