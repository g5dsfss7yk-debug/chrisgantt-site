"""Nov 23 2026: test the three gaps Chris asked about, one at a time, then together.
  A. opponent-adjusted ratings  B. pass rushers Out/Doubtful  C. special teams split by unit
Walk-forward (every season predicted by a fit on earlier seasons only), graded at the game-day
line. Settings are chosen on 2015-22 only; 2023-26 is the check. Break-even 52.4% at -110.
    PYTHONPATH=. python v2/test_three.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl, extra_data

BASE = [k for k in nfl.STATS if k not in ("rz", "c_epa", "c_sr", "c_explosive")]   # the pre-Nov-23 inputs
nfl.SPREAD_SKIP = set()
nfl.QB_VAL_SPREAD = False                    # tests start from the pre-Nov-23 card


def grade(d, kind, line):
    p = nfl.walk_forward(d, kind, line)
    p = p[p.result.notna()]
    e = p.pred - p[line]
    a = (p.result if kind == "spread" else p.total) - p[line]
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=p.index)
    o, n, b = p.season <= 2022, p.season >= 2023, e.abs() >= 1
    f = lambda m: f"{w[m].mean():.1%} of {int(w[m].notna().sum())}"
    return f"all {f(o)} / {f(n)} | edge 1+ {f(o & b)} / {f(n & b)}"


def run(name, opp=0.0, st=False, rush=False, keep_st=False):
    nfl.OPP_ADJ, nfl.ST_SPLIT, nfl.RUSH_OUT = opp, st, rush
    nfl.STATS = BASE if not st else [k for k in BASE if keep_st or k != "st_epa"] + extra_data.ST_UNITS
    d = nfl.build()
    print(f"\n{name}   (2015-22 / 2023-26)")
    print("  spread:", grade(d, "spread", "spread_line"))
    print("  total: ", grade(d, "total", "total_line"), flush=True)


if __name__ == "__main__":
    run("BASELINE (current card)")
    run("A. opponent-adjusted, half strength", opp=0.5)
    run("A. opponent-adjusted, full strength", opp=1.0)
    run("B. pass rushers Out/Doubtful", rush=True)
    run("C. special teams split (replaces the one ST number)", st=True)
    run("C. special teams split (added to the one ST number)", st=True, keep_st=True)
    run("A full + B + C replace", opp=1.0, st=True, rush=True)
    nfl.OPP_ADJ, nfl.ST_SPLIT, nfl.RUSH_OUT, nfl.STATS = 0.0, False, False, BASE
