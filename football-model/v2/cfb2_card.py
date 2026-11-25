"""College card from the rebuilt model (v2/cfb2.py). EVERY game gets a spread and a total lean (Chris,
Nov 24: "the model needs to lean one way or the other"). Spread at edge 2+ pts = TESTED PICK (55.2% of 507
/ 54.3% of 361, 2018-22 / 2023-26); under 2 pts = LEAN (all games 50.1% / 52.0%, about a coin flip).
Total = LEAN (all games 50.8% / 50.9%; no tested college total from this model). Lines: DraftKings via CollegeFootballData (no odds-API credits), or --line.
    PYTHONPATH=. python v2/cfb2_card.py --date 2026-11-28 [--line "Iowa=-7.5"]"""
import argparse, json, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import cfb2

ap = argparse.ArgumentParser(); ap.add_argument("--date"); ap.add_argument("--line", action="append", default=[])
ap.add_argument("--total", action="append", default=[], help='"Team=46.5" (either team in the game)')
a = ap.parse_args()
d = cfb2.build()
done = d[d.result.notna() & d.espn_spread.notna() & (d.season >= 2015)]
m = cfb2.fit(done, "spread")
mt = cfb2.fit(done[done.espn_total.notna()], "total")
day = pd.Timestamp(a.date) if a.date else d[d.result.isna()].gameday.min()
g = d[(d.gameday == day) & d.result.isna()].copy()
if g.empty:
    sys.exit(f"no unplayed games on {day:%Y-%m-%d}")
# DraftKings lines from CollegeFootballData (the session proxy holds the key)
dk = {}
for wk in g.week.unique():
    url = f"https://api.collegefootballdata.com/lines?year={int(g.season.iloc[0])}&week={int(wk)}&seasonType={g.season_type.iloc[0]}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer x"}), timeout=30) as r:
            for x in json.load(r):
                for l in x["lines"]:
                    if l["provider"] == "DraftKings" and l.get("spread") is not None:
                        dk[x["id"]] = (-float(l["spread"]), l.get("overUnder"), l.get("homeMoneyline"), l.get("awayMoneyline"))
    except Exception as e:
        print(f"warning: no CFBD lines ({e})")
over, tover = {}, {}
for s in a.line:
    t, v = s.rsplit("=", 1); over[t.strip()] = float(v)
for s in a.total:
    t, v = s.rsplit("=", 1); tover[t.strip()] = float(v)
print(f"College card {day:%a %m/%d/%Y} (rebuilt model). TESTED PICK = spread edge 2+ pts (55.2% / 54.3%, 2018-22 / 2023-26).")
print("LEAN = the model's side with no tested edge (spread 50.1% / 52.0%, total 50.8% / 50.9%) - $2 fun only.")
for r in g.sort_values("start").itertuples():
    if r.home_team in over:
        line = -over[r.home_team]
    elif r.away_team in over:
        line = over[r.away_team]
    elif r.game_id in dk:
        line = dk[r.game_id][0]
    else:
        print(f"\n{r.away_team} @ {r.home_team}: no DraftKings line found - give it with --line"); continue
    row = pd.DataFrame([r._asdict()]).assign(espn_spread=line)
    pred = m.predict(cfb2.X(row, pd.Series([line]), "spread"))[0]
    edge = pred - line
    side = r.home_team if edge > 0 else r.away_team
    pts = -line if edge > 0 else line
    thin = min(r.home_n if pd.notna(r.home_n) else 0, r.away_n if pd.notna(r.away_n) else 0) < 3
    print(f"\n{r.kickoff_et:%I:%M%p} ET  {r.away_team} @ {r.home_team}   DK: {r.home_team} {-line:+g}   model: {r.home_team} {-pred:+.1f}")
    if abs(edge) >= cfb2.EDGE_MIN and not thin:
        print(f"  >> TESTED PICK  {side} {pts:+g}   edge {abs(edge):.1f} pts   (edge 2+: 55.2% of 507 / 54.3% of 361)")
    else:
        print(f"  SPREAD LEAN  {side} {pts:+g}   edge {abs(edge):.1f} pts{' (a team has under 3 games of data)' if thin else ''}   (50.1% / 52.0%)")
    winner = r.home_team if pred > 0 else r.away_team
    print(f"  WINNER LEAN  {winner}")
    tot = tover.get(r.home_team, tover.get(r.away_team, dk.get(r.game_id, (None, None))[1]))
    if tot is not None:
        tot = float(tot)
        pt = mt.predict(cfb2.X(row.assign(espn_total=tot), pd.Series([tot]), "total"))[0]
        print(f"  TOTAL LEAN  {'Over' if pt > tot else 'Under'} {tot:g}   model {pt:.1f}   (50.8% / 50.9%)")
    else:
        print("  TOTAL LEAN  no DraftKings total found - give it with --total")
