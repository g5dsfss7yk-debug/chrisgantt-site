"""Nov 23 2026: four more inputs, tested like v2/test_three.py (walk-forward, game-day line,
2015-22 / 2023-26, break-even 52.4%).
  1. starting QB's own value  2. referee crew (totals)  3. pace and pass rate  4. red-zone TD rate
    PYTHONPATH=. python v2/test_four.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl, extra_data
from v2.test_three import grade

BASE = [k for k in nfl.STATS if k not in ("rz", "c_epa", "c_sr", "c_explosive")]   # the pre-Nov-23 inputs
nfl.SPREAD_SKIP = set()
nfl.QB_VAL_SPREAD = False                    # tests start from the pre-Nov-23 card
PACE = ["sec_per_play", "neutral_pass", "no_huddle"]


def run(name, qb=False, ref=False, pace=False, rz=False):
    nfl.QB_VAL, nfl.REF_TOT = qb, ref
    nfl.STATS = BASE + (PACE if pace else []) + (["rz"] if rz else [])
    d = nfl.build()
    print(f"\n{name}   (2015-22 / 2023-26)")
    print("  spread:", grade(d, "spread", "spread_line"))
    print("  total: ", grade(d, "total", "total_line"), flush=True)
    return d


if __name__ == "__main__":
    v = extra_data.qb_values()
    print(f"QB prior (new QBs' EPA/play, seasons before 2015): {v.attrs['prior']:+.3f}")
    run("BASELINE (current card)")
    d = run("1. starting QB's own value", qb=True)
    x = d[(d.season == 2026) & d.result.isna()].head(16)
    print(x[["week", "away_qb_name", "away_qb_val", "home_qb_name", "home_qb_val"]].round(3).to_string())
    run("2. referee crew, totals", ref=True)
    run("3. pace and pass rate", pace=True)
    run("4. red-zone TD rate", rz=True)
    run("1 + 2 + 3 + 4", qb=True, ref=True, pace=True, rz=True)
    nfl.QB_VAL, nfl.REF_TOT, nfl.STATS = False, False, BASE
