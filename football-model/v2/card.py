"""v2 card: a pick on every game (spread, total, winner) against DraftKings' current lines,
each with the tested record of its size bucket (walk-forward, v2/test_nfl.py, test_teaser.py).

    python v2/card.py [--week N] [--before HH:MM]   (ET kickoff cutoff, e.g. 13:05 for early games)
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl
from nflmodel import odds, data
from run import NICK

# Tested records, walk-forward, 2015-22 / 2023-26 (v2/test_nfl.py, v2/test_teaser.py, re-run Nov 15 after
# the wind / scaling fixes). The model is fit on the game-day line and the pick is graded at that line.
# Break-even at -110 is 52.4%; a 2-team -120 teaser needs 73.9% per leg.
SPREAD_REC = [(2.0, "57.0% of 214 (2015-22) / 58.1% of 62 (2023-26) - few games, not proven"),
              (1.0, "52.8% of 849 (2015-22) / 55.0% of 311 (2023-26)"),
              (0.0, "52.4% (2015-22) / 50.7% (2023-26), all games")]
TOTAL_REC = [(1.0, "55.8% (2015-22) / 50.8% (2023-26)"), (0.0, "53.2% (2015-22) / 51.7% (2023-26), all games")]
TEASE = {(1, 2.5): "69.7% (2015-22) / 77.9% (2023-26) per leg", (3, 3.5): "76.9% / 70.4% per leg",
         (-7.5, -3.5): "70.0% / 74.6% per leg"}

ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int); ap.add_argument("--before"); ap.add_argument("--after"); ap.add_argument("--cached", action="store_true")
a = ap.parse_args()
d = nfl.build()
season = data.current_season()
wk = a.week or int(d[(d.season == season) & d.result.isna()]["week"].min())
done = d[d.result.notna() & (d.season >= 2009)]
ms = nfl.fit(done[done.spread_line.notna()], "spread", "spread_line")
mt = nfl.fit(done[done.total_line.notna()], "total", "total_line")
g = d[(d.season == season) & (d.week == wk) & d.result.isna()].copy()
if a.before:
    g = g[g.gametime.astype(str) <= a.before]
if a.after:
    g = g[g.gametime.astype(str) > a.after]
odds.TTL = 10**9 if a.cached else 0
ev = odds._get("/sports/americanfootball_nfl/odds", bookmakers="draftkings", markets="spreads,totals,h2h", oddsFormat="american")
for r in g.sort_values(["gameday", "gametime"]).itertuples(index=False):
    e = [x for x in ev if NICK[r.home_team] in x["home_team"] and NICK[r.away_team] in x["away_team"]]
    kick = pd.Timestamp(f"{pd.Timestamp(r.gameday):%Y-%m-%d} {r.gametime}")
    if kick <= data._now_et():                           # DK's line is now an in-game line: no pregame pick
        print(f"\n{r.away_team} @ {r.home_team}: already started - DK's line is a live line, no pregame pick"); continue
    if not e or not e[0]["bookmakers"]:
        print(f"{r.away_team} @ {r.home_team}: no DK line"); continue
    mk = {m["key"]: m["outcomes"] for m in e[0]["bookmakers"][0]["markets"]}
    sp = next(o for o in mk["spreads"] if NICK[r.home_team] in o["name"])
    dk_line = -sp["point"]                                  # + = home favored
    tot = mk["totals"][0]["point"]
    ml = {("home" if NICK[r.home_team] in o["name"] else "away"): o["price"] for o in mk.get("h2h", [])}
    row = pd.DataFrame([r._asdict()])
    pred = ms.predict(nfl.X(row, pd.Series([dk_line]), "spread"))[0]
    ptot = mt.predict(nfl.X(row, pd.Series([tot]), "total"))[0]
    edge = pred - dk_line
    home = edge > 0
    team = r.home_team if home else r.away_team
    pts = -dk_line if home else dk_line
    rec = next(t for lo, t in SPREAD_REC if abs(edge) >= lo)
    t_et = str(r.gametime); h, m = map(int, t_et.split(":"))
    print(f"\n{r.away_team} @ {r.home_team}  {h-1}:{m:02d} CT   QBs: {r.away_qb_name} / {r.home_qb_name}")
    print(f"  SPREAD  {team} {pts:+g}   model margin {pred:+.1f} (home), edge {abs(edge):.1f} pts   tested {rec}")
    print(f"  WINNER  {r.home_team if pred > 0 else r.away_team} ML {ml.get('home' if pred > 0 else 'away')}")
    print(f"  TOTAL   {'Over' if ptot > tot else 'Under'} {tot:g}   model {ptot:.1f}   edge {abs(ptot - tot):.1f}   tested {next(t for lo, t in TOTAL_REC if abs(ptot - tot) >= lo)}")
    if 1.5 <= abs(dk_line) <= 2.5:                       # v2/dig.py: every dog in this range, model not needed
        dog = r.away_team if dk_line > 0 else r.home_team
        low = "total 44 or less: 75.9% / 77.4% / 78.9%" if tot <= 44 else "total over 44: 65.0% / 76.8% / 75.5%"
        print(f"  BEST TEASER LEG  {dog} {abs(dk_line) + 6:+g}   every dog +1.5..+2.5 teased 6: 72.7% (1999-2014) / 77.0% (2015-22) / "
              f"77.3% (2023-26); {low}. Needs 73.9% at -120, 75.2% at -130 - check DK's teaser price")
    for (lo, hi), t in TEASE.items():
        if lo <= pts <= hi:
            print(f"  TEASER  {team} {pts + 6:+g}   tested {t}")
