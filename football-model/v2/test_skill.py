"""Nov 23 2026: backup RBs, WRs and TEs. Input = share of a team's last-8-game scrimmage yards made by
RB/WR/TE listed Out or Doubtful that week (so backups play). Same test as v2/test_four.py:
walk-forward, game-day line, 2015-22 / 2023-26, starting from the current card.
    PYTHONPATH=. python v2/test_skill.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl
from v2.test_three import grade
nfl.QB_VAL_SPREAD = True        # test_three turns these off on import; the current card has them on
nfl.SPREAD_SKIP = {"epa", "sr", "explosive"}

if __name__ == "__main__":
    for name, mode, kinds in (("CURRENT CARD", "", ()), ("all skill players, one number", "all", ("spread", "total")),
                              ("RB, WR, TE separately", "split", ("spread", "total"))):
        nfl.SKILL_OUT, nfl.SKILL_KINDS = mode, kinds
        d = nfl.build()
        print(f"\n{name}   (2015-22 / 2023-26)")
        print("  spread:", grade(d, "spread", "spread_line"))
        print("  total: ", grade(d, "total", "total_line"), flush=True)
    so = d[d.season >= 2009][["home_skill_out", "away_skill_out"]]
    print("\ngames where a team had 20%+ of its RB/WR/TE yards Out/Doubtful:", int((so.max(axis=1) >= 0.2).sum()), "of", len(so))
    nfl.SKILL_OUT = ""
