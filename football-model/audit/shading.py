"""Audit F: does DraftKings overprice popular players' overs? (No game results needed.)

Idea (Chris, Nov 10): DK sees what its customers bet, and customers mostly bet overs on popular
players, so DK can charge more for those overs. Test: at the sharp books' own main number, compare
DK's implied chance for the Over with the sharp no-vig chance. The gap is what DK charges above
fair. If it is bigger for stars than for lesser players, bet the lesser players' overs.

"Star" = the player with the highest model projection on his team in that market; everyone else
is "other". Input: picks/rungs/*.csv from `run.py props --scan ...` (pregame and live snapshots).

    python audit/shading.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd

from nflmodel import data

files = sorted((data.ROOT / "picks" / "rungs").glob("*.csv"))
d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()
if d.empty or "sharp_main" not in d:
    raise SystemExit("no saved rungs with sharp main lines yet: run `run.py props --week N --scan all`")
d = d[d["pregame"].astype(str) == "True"].dropna(subset=["sharp_main"])
# the DK rung at the sharp main number ("X+" = Over X-0.5)
at = d[(d["rung"] - 0.5 - d["sharp_main"]).abs() < 0.01].copy()
at = at.sort_values("snapshot_utc").drop_duplicates(["game_id", "player", "market"], keep="last")
if at.empty:
    raise SystemExit("no DK rung sits exactly on a sharp main line yet")
rank = at.groupby(["game_id", "team", "market"])["proj"].rank(ascending=False, method="first")
at["tier"] = (rank == 1).map({True: "star", False: "other"})
at["dk_over_fair"] = at["dk"] - at["sharp_main_fair"]
print(f"{len(at)} player-markets from {at['game_id'].nunique()} games (DK Over vs sharp no-vig at the same number)\n")
print(at.groupby(["market", "tier"]).agg(n=("dk_over_fair", "size"), dk=("dk", "mean"), fair=("sharp_main_fair", "mean"),
                                         dk_charges_above_fair=("dk_over_fair", "mean")).round(3).to_string())
print("\nBigger 'dk_charges_above_fair' = a worse price. If stars pay clearly more than others across")
print("enough games (aim for 100+ player-markets per tier), bet the 'other' players' overs.")
