import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl
g, p = nfl.team_games()
n = nfl.data.load_nfelo()[["season", "week", "home_fr", "home_line_open"]]
def score(kind, col, lo=1.0):
    q = nfl.walk_forward(d, kind, col); q = q[q.result.notna()]
    e = q.pred - q[col]; a = (q.result if kind == "spread" else q.total) - q[col]
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=q.index)
    out = []
    for per in (q.season <= 2022, q.season >= 2023):
        out.append(f"{w[per].mean():.3f}/{w[per & (e.abs() >= lo)].mean():.3f}({(per & (e.abs() >= lo)).sum()})")
    return " ".join(out)
base = nfl.build()
for hl in (4, 6, 10):
    for carry in (0.5, 0.65, 0.8):
        nfl.HALF_LIFE, nfl.CARRY = hl, carry
        rt = nfl.ratings(g, p)
        d = base.drop(columns=[c for c in base if c.startswith(("home_o_", "home_d_", "away_o_", "away_d_", "home_p", "away_p"))]).merge(rt.drop(columns=["home_n","away_n"]), on="game_id")
        print(hl, carry, "spread/open", score("spread", "spread_open"), "| total/close", score("total", "total_line"), flush=True)
