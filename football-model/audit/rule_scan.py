"""Audit G: search NFL data for simple betting rules that beat the CLOSING line.

Not a model: plain rules ("road dog off a bye", "total moved down 2+ and wind 15+, under"),
graded against the closing spread/total (what a bettor actually gets near kickoff).
Guard against fooling ourselves (thousands of rules -> some look good by luck):
  1. FIND:     rules winning 55%+ on 2009-2017 (n >= 100)
  2. VALIDATE: keep only those also winning 53%+ on 2018-2022 (n >= 40)
  3. CONFIRM:  report their 2023-2026 record; a bet needs 52.4% at -110
The number of rules tried is printed, so the survivors can be judged against chance.

    python audit/rule_scan.py
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd

from nflmodel import pipeline

df = pipeline.load()
d = df[(df["season"] >= 2009) & df["result"].notna() & df["spread_line"].notna() & df["total_line"].notna()].copy()
from nflmodel import data
raw = data.load_games()[["game_id", "home_rest", "away_rest", "roof", "home_qb_id", "away_qb_id"]]
d = d.drop(columns=[c for c in ("home_rest", "away_rest", "roof") if c in d]).merge(raw, on="game_id", how="left")
d = d.sort_values("gameday").reset_index(drop=True)
# QB change: this game's starter differs from the team's previous starter (same season)
lastqb, hq, aq = {}, [], []
for r in d.itertuples(index=False):
    hq.append(int(lastqb.get((r.season, r.home_team), r.home_qb_id) != r.home_qb_id))
    aq.append(int(lastqb.get((r.season, r.away_team), r.away_qb_id) != r.away_qb_id))
    lastqb[(r.season, r.home_team)], lastqb[(r.season, r.away_team)] = r.home_qb_id, r.away_qb_id
d["home_qb_change"], d["away_qb_change"] = hq, aq

# previous game margin for each team (from that team's side)
last = {}
prev_home, prev_away = [], []
for r in d.itertuples(index=False):
    prev_home.append(last.get((r.season, r.home_team), np.nan))
    prev_away.append(last.get((r.season, r.away_team), np.nan))
    last[(r.season, r.home_team)] = r.result
    last[(r.season, r.away_team)] = -r.result
d["home_prev"], d["away_prev"] = prev_home, prev_away

line = d["spread_line"]                       # + = home favored by that many
dog_line = line.abs()
home_dog = line < 0
open_ = d["spread_open"]
move_home = line - open_                      # + = line moved toward the home team
tmove = d["total_line"] - d["total_open"]
gt = d["gametime"].astype(str)
prime = (gt >= "19:00") | pd.to_datetime(d["gameday"]).dt.day_name().isin(["Monday", "Thursday"])

C = {  # game conditions
    "pk-2.5": dog_line <= 2.5, "line 3": dog_line == 3, "3.5-6.5": dog_line.between(3.5, 6.5),
    "line 7": dog_line == 7, "7.5-10": dog_line.between(7.5, 10), "10.5+": dog_line >= 10.5,
    "home dog": home_dog, "road dog": ~home_dog & (line != 0),
    "division": d["div_game"] == 1, "primetime": prime, "late season (wk14+)": d["week"] >= 14,
    "early season (wk1-4)": d["week"] <= 4,
    "home short week": d["home_rest"] <= 5, "away short week": d["away_rest"] <= 5,
    "home off bye": d["home_rest"] >= 12, "away off bye": d["away_rest"] >= 12,
    "line moved to home 1.5+": move_home >= 1.5, "line moved to away 1.5+": move_home <= -1.5,
    "total up 1.5+": tmove >= 1.5, "total down 1.5+": tmove <= -1.5,
    "total <40": d["total_line"] < 40, "total 50+": d["total_line"] >= 50,
    "wind 15+": d["wind"].fillna(0) >= 15, "cold <=32F": d["temp"].fillna(60) <= 32,
    "dome": d["roof"].isin(["dome", "closed"]),
    "home lost by 14+ last game": d["home_prev"] <= -14, "away lost by 14+ last game": d["away_prev"] <= -14,
    "home won by 14+ last game": d["home_prev"] >= 14, "away won by 14+ last game": d["away_prev"] >= 14,
}
if "home_qb_change" in d:
    C["home QB change"] = d["home_qb_change"] == 1
    C["away QB change"] = d["away_qb_change"] == 1
C = {k: v.fillna(False).astype(bool) for k, v in C.items()}

# bet outcomes vs the closing number (NaN = push)
margin = d["result"] - line                    # home cover margin
T = {
    "dog ATS": np.where(home_dog, margin, -margin), "favorite ATS": np.where(home_dog, -margin, margin),
    "home ATS": margin, "away ATS": -margin,
    "over": d["total"] - d["total_line"], "under": d["total_line"] - d["total"],
}
T = {k: pd.Series(np.where(v == 0, np.nan, v > 0), index=d.index) for k, v in T.items()}

period = np.select([d["season"] <= 2017, d["season"] <= 2022], ["find", "validate"], "confirm")

rows, tried = [], 0
names = list(C)
for k in (1, 2):
    for combo in itertools.combinations(names, k):
        mask = np.logical_and.reduce([C[c].values for c in combo])
        if mask.sum() < 150:
            continue
        for tname, won in T.items():
            tried += 1
            w = won[mask]
            per = {}
            for p in ("find", "validate", "confirm"):
                x = w[period[mask] == p].dropna()
                per[p] = (len(x), x.mean() if len(x) else np.nan)
            if per["find"][0] >= 100 and per["find"][1] >= 0.55 and per["validate"][0] >= 40 and per["validate"][1] >= 0.53:
                rows.append({"rule": " + ".join(combo), "bet": tname,
                             "2009-17": f"{per['find'][1]:.1%} ({per['find'][0]})",
                             "2018-22": f"{per['validate'][1]:.1%} ({per['validate'][0]})",
                             "2023-26": f"{per['confirm'][1]:.1%} ({per['confirm'][0]})",
                             "confirm_rate": per["confirm"][1], "confirm_n": per["confirm"][0]})
print(f"rules x bets tried: {tried}")
print("by luck alone, about 1 in 20 would pass step 1 and 1 in 4 of those step 2 - so expect some false survivors\n")
out = pd.DataFrame(rows)
if out.empty:
    print("no rule passed both FIND (55%+) and VALIDATE (53%+)")
else:
    out = out.sort_values("confirm_rate", ascending=False)
    print(out.drop(columns=["confirm_rate", "confirm_n"]).to_string(index=False))
    ok = out[(out["confirm_rate"] >= 0.524) & (out["confirm_n"] >= 30)]
    print(f"\npassed all three (2023-26 >= 52.4%, n>=30): {len(ok)} of {len(out)} survivors")
