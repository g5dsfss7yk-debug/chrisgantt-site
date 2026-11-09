"""Every bet I recommend (parlays, teasers, props, singles) is logged here and graded from ESPN
box scores, so the record shows the real track record of the advice, not only the model's picks.

Legs (one per --leg), all "X or more" for props since DraftKings ladders are overs:
  spread:TEAM:-3.5          team covers (teaser legs: give the teased number)
  ml:TEAM                   team wins
  total:TEAM:over:45.5      game total (TEAM = either team in the game)
  prop:Player Name:stat:N   player gets N or more of stat; stats: passing_yards, passing_tds,
                            completions, rushing_yards, receiving_yards, receptions, anytime_td
TEAM is the ESPN abbreviation for NFL (GB, NE) or the school name for college (LSU).

  python recs.py add --date 2026-11-08 --league nfl --kind parlay --tier fun --stake 2 \
      --leg "prop:Matthew Golden:receiving_yards:40" --leg "prop:Rhamondre Stevenson:rushing_yards:40"
  python recs.py grade        # fills results for finished games and prints the record
"""
from __future__ import annotations

import argparse
import json
import urllib.request

import pandas as pd

from nflmodel.data import ROOT

LOG = ROOT / "picks" / "recs.csv"
COLS = ["id", "date", "league", "kind", "tier", "stake", "odds", "legs", "note", "result", "leg_results"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/{lg}/{what}"
STAT = {"passing_yards": ("passing", "YDS"), "passing_tds": ("passing", "TD"),
        "completions": ("passing", "C/ATT"), "rushing_yards": ("rushing", "YDS"),
        "receiving_yards": ("receiving", "YDS"), "receptions": ("receiving", "REC")}


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def _league(lg):
    return "nfl" if lg == "nfl" else "college-football"


def _events(lg, day):
    url = ESPN.format(lg=_league(lg), what="scoreboard") + f"?dates={pd.Timestamp(day):%Y%m%d}&limit=400"
    if lg != "nfl":
        url += "&groups=80"
    return _get(url).get("events", [])


def _team_match(c, team):
    t = c["team"]
    names = {t.get("abbreviation", ""), t.get("location", ""), t.get("displayName", ""), t.get("shortDisplayName", "")}
    return team.lower() in {n.lower() for n in names if n}


def _game(events, team):
    for e in events:
        comp = e["competitions"][0]
        if any(_team_match(c, team) for c in comp["competitors"]):
            return e, comp
    return None, None


def _summary(lg, event_id):
    return _get(ESPN.format(lg=_league(lg), what="summary") + f"?event={event_id}")


def _player_stats(lg, events, name):
    """{(category, label): value} for a player from the day's box scores, or None."""
    for e in events:
        summ = _summary(lg, e["id"])
        if not summ["header"]["competitions"][0]["status"]["type"]["completed"]:
            continue
        box = summ.get("boxscore", {})
        found, out = False, {}
        for team in box.get("players", []):
            for cat in team["statistics"]:
                for a in cat["athletes"]:
                    if a["athlete"]["displayName"].lower() == name.lower():
                        found = True
                        for lab, v in zip(cat["labels"], a["stats"]):
                            out[(cat["name"], lab)] = v
        if found:
            return out
    return None


def grade_leg(lg, day, leg):
    """'win', 'loss', 'push' or 'pending'."""
    events = _events(lg, day)
    p = leg.split(":")
    if p[0] == "prop":
        name, stat, need = p[1], p[2], float(p[3])
        s = _player_stats(lg, events, name)
        if s is None:
            return "pending"
        if stat == "anytime_td":
            val = sum(float(s.get((c, "TD"), 0) or 0) for c in ("rushing", "receiving"))
        else:
            raw = s.get(STAT[stat], "0")
            val = float(str(raw).split("/")[0])
        return "win" if val >= need else "loss"
    e, comp = _game(events, p[1])
    if e is None:
        return "pending"
    if not comp["status"]["type"]["completed"]:
        # the scoreboard can lag; the game's own summary has the final status and score
        comp = _summary(lg, e["id"])["header"]["competitions"][0]
        if not comp["status"]["type"]["completed"]:
            return "pending"
    mine = next(c for c in comp["competitors"] if _team_match(c, p[1]))
    other = next(c for c in comp["competitors"] if c is not mine)
    m, o = float(mine["score"]), float(other["score"])
    if p[0] == "ml":
        return "win" if m > o else "loss" if m < o else "push"
    if p[0] == "spread":
        d = m - o + float(p[2])
    elif p[0] == "total":
        d = (m + o - float(p[3])) * (1 if p[2] == "over" else -1)
    else:
        raise ValueError(f"unknown leg {leg}")
    return "win" if d > 0 else "loss" if d < 0 else "push"


def load():
    return pd.read_csv(LOG, dtype=str, keep_default_na=False) if LOG.exists() else pd.DataFrame(columns=COLS)


def cmd_add(a):
    df = load()
    for leg in a.leg:  # validate the format now, not at grading time
        kind = leg.split(":")[0]
        assert kind in ("spread", "ml", "total", "prop"), f"bad leg: {leg}"
        if kind == "prop":
            assert leg.split(":")[2] in list(STAT) + ["anytime_td"], f"bad stat in: {leg}"
    row = {"id": int(df["id"].astype(int).max()) + 1 if len(df) else 1, "date": a.date, "league": a.league,
           "kind": a.kind, "tier": a.tier, "stake": a.stake, "odds": a.odds or "", "legs": " | ".join(a.leg),
           "note": a.note or "", "result": "pending", "leg_results": ""}
    pd.concat([df, pd.DataFrame([row])], ignore_index=True).to_csv(LOG, index=False)
    print(f"logged #{row['id']}: {row['kind']} {row['legs']}")


def cmd_grade(a):
    df = load()
    for i, r in df.iterrows():
        if r["result"] != "pending":
            continue
        res = [grade_leg(r["league"], r["date"], leg) for leg in str(r["legs"]).split(" | ")]
        df.at[i, "leg_results"] = " ".join(res)
        if "loss" in res:
            df.at[i, "result"] = "loss"
        elif "pending" in res:
            df.at[i, "result"] = "pending"
        elif all(x == "push" for x in res):
            df.at[i, "result"] = "push"
        else:
            df.at[i, "result"] = "win"
    df.to_csv(LOG, index=False)
    for r in df.itertuples(index=False):
        print(f"#{r.id} {r.date} {r.league} {r.kind:7} {r.tier:6} {r.result:8} {r.legs}  [{r.leg_results}]")
    done = df[df["result"].isin(["win", "loss"])]
    for tier, g in done.groupby("tier"):
        w = (g["result"] == "win").sum()
        print(f"{tier}: {w}-{len(g) - w}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("--date", required=True)
    ad.add_argument("--league", choices=["nfl", "cfb"], required=True)
    ad.add_argument("--kind", choices=["single", "parlay", "teaser"], required=True)
    ad.add_argument("--tier", choices=["backed", "fun"], required=True,
                    help="backed = one of the backtested NFL bets; fun = no proven edge")
    ad.add_argument("--stake", type=float, default=2)
    ad.add_argument("--odds")
    ad.add_argument("--note")
    ad.add_argument("--leg", action="append", required=True)
    ad.set_defaults(f=cmd_add)
    sub.add_parser("grade").set_defaults(f=cmd_grade)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
