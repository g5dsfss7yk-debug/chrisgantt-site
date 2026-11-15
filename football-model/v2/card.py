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

# tested records (2023-26, v2 walk-forward). Spread vs opening line, edge = |model - line|.
SPREAD_REC = [(1.0, "55.0% (333 picks)"), (0.0, "51.3% (all games)")]
TOTAL_REC = "51.2% (493 picks, totals vs close 2023-26)"
TEASE = {(1, 2.5): "79.3% per leg (135)", (3, 3.5): "72.8% per leg (136)"}

ap = argparse.ArgumentParser(); ap.add_argument("--week", type=int); ap.add_argument("--before")
a = ap.parse_args()
d = nfl.build()
season = data.current_season()
wk = a.week or int(d[(d.season == season) & d.result.isna()]["week"].min())
done = d[d.result.notna() & (d.season >= 2009)]
ms = nfl.fit(done[done.spread_open.notna()], "spread", "spread_open")
mt = nfl.fit(done[done.total_line.notna()], "total", "total_line")
g = d[(d.season == season) & (d.week == wk) & d.result.isna()].copy()
if a.before:
    g = g[g.gametime.astype(str) <= a.before]
odds.TTL = 0
ev = odds._get("/sports/americanfootball_nfl/odds", bookmakers="draftkings", markets="spreads,totals,h2h", oddsFormat="american")
for r in g.sort_values(["gameday", "gametime"]).itertuples(index=False):
    e = [x for x in ev if NICK[r.home_team] in x["home_team"] and NICK[r.away_team] in x["away_team"]]
    if not e or not e[0]["bookmakers"]:
        print(f"{r.away_team} @ {r.home_team}: no DK line"); continue
    mk = {m["key"]: m["outcomes"] for m in e[0]["bookmakers"][0]["markets"]}
    sp = next(o for o in mk["spreads"] if NICK[r.home_team] in o["name"])
    dk_line = -sp["point"]                                  # + = home favored
    tot = mk["totals"][0]["point"]
    ml = {("home" if NICK[r.home_team] in o["name"] else "away"): o["price"] for o in mk.get("h2h", [])}
    row = pd.DataFrame([r._asdict()])
    pred = ms.predict(nfl.X(row, row["spread_open"].fillna(dk_line), "spread"))[0]
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
    print(f"  TOTAL   {'Over' if ptot > tot else 'Under'} {tot:g}   model {ptot:.1f}   tested {TOTAL_REC}")
    for (lo, hi), t in TEASE.items():
        if lo <= pts <= hi:
            print(f"  TEASER  {team} {pts + 6:+g}   tested {t}")
