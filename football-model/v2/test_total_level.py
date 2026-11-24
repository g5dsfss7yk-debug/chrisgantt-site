"""Nov 24 2026 (Chris: "unders have been killing us - fix it, but don't over-correct, unders happen").
Fix tested: shift ONLY the model's scoring level for a season by a share of how far its totals missed
(actual minus model, out of sample) over the previous 1-2 full seasons. Nothing else changes, and only
completed seasons are used (no chasing last week). Walk-forward, game-day line.
    PYTHONPATH=. python v2/test_total_level.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl

d = nfl.build()
p = nfl.walk_forward(d, "total", "total_line")
p = p[p.result.notna()].copy()
miss = (p.total - p.pred).groupby(p.season).mean()          # out-of-sample miss per season
print("model's average miss by season (actual minus model, + = games scored MORE than the model said):")
print("  " + "  ".join(f"{s}:{v:+.1f}" for s, v in miss.items()))


def grade(q, lab):
    e = q.pred2 - q.total_line; a = q.total - q.total_line
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=q.index)
    out = []
    for per, m in (("2015-22", q.season <= 2022), ("2023-26", q.season >= 2023), ("2026", q.season == 2026)):
        o, u, b = m & (e > 0), m & (e < 0), m & (e.abs() >= 1)
        out.append(f"{per}: all {w[m].mean():.1%}, edge 1+ {w[b].mean():.1%}, Over picks {o.sum() / m.sum():.0%} "
                   f"(won {w[o].mean():.1%}) Unders won {w[u].mean():.1%}")
    print(f"\n{lab}\n  " + "\n  ".join(out))


for share, years in ((0.0, 1), (0.5, 1), (0.5, 2), (1.0, 2)):
    shift = {s: share * miss.loc[[y for y in range(s - years, s) if y in miss.index]].mean()
             if any(y in miss.index for y in range(s - years, s)) else 0.0 for s in p.season.unique()}
    p["pred2"] = p.pred + p.season.map(shift)
    lab = "CURRENT (no shift)" if share == 0 else f"shift by {share:.0%} of the average miss over the last {years} season(s)"
    grade(p, lab + (f"  - 2026 shift {shift[2026]:+.1f} pts" if share else ""))
