"""Nov 23 2026 batch: every game-model variable not yet tested (Chris: "test all of them").
Each added alone to the current card, same walk-forward test (game-day line, 2015-22 / 2023-26).
Kept only if it helps in BOTH periods.
    PYTHONPATH=. python v2/test_game_batch.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl
from v2.test_recency import wf

BASE = list(nfl.STATS)
TESTS = [("CURRENT CARD", {}), ("turnover + close-game luck", {"LUCK": True}),
         ("time zones, West team early, division, byes", {"TRAVEL": True}),
         ("coach tenure, new coach, returning starters", {"COACH": True}),
         ("offensive linemen Out/Doubtful", {"OL": True}), ("totals: rain, snow, cold, turf", {"TOT_WX": True})]
if __name__ == "__main__":
    for name, flags in TESTS:
        for k, v in flags.items():
            setattr(nfl, k, v)
        nfl.STATS = BASE + (["fumluck"] if flags.get("LUCK") else [])
        d = nfl.build()
        print(f"\n{name}   (2015-22 / 2023-26)\n  spread {wf(d, 'spread', 'spread_line', None)}\n  total  {wf(d, 'total', 'total_line', None)}", flush=True)
        for k in flags:
            setattr(nfl, k, False)
    nfl.STATS = BASE
