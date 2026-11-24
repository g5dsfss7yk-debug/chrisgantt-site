"""Nov 23 2026 (Chris: "matchups like run game vs run defense"). Rule set BEFORE running: adopt only if
spread picks improve in BOTH periods (all games and edge 1+). Walk-forward, game-day line, 2015-22 / 2023-26.
  A. run offense vs run defense, pass offense vs pass defense (each unit's EPA/play and success rate)
  B. A + "strength meets weakness": a good run offense facing a bad run defense counts extra (same for pass)
    PYTHONPATH=. python v2/test_matchups.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from v2 import nfl
from v2.test_recency import wf

BASE = list(nfl.STATS)
if __name__ == "__main__":
    for name, split, mm in (("CURRENT CARD", False, False), ("A. run vs run D, pass vs pass D", True, False),
                            ("B. A + strength meets weakness", True, True)):
        nfl.SPLIT, nfl.MISMATCH = split, mm
        nfl.STATS = BASE + (nfl.SPLIT_STATS if split else [])
        d = nfl.build()
        print(f"\n{name}   (2015-22 / 2023-26)\n  spread {wf(d, 'spread', 'spread_line', None)}\n  total  {wf(d, 'total', 'total_line', None)}", flush=True)
    nfl.SPLIT = nfl.MISMATCH = False; nfl.STATS = BASE
