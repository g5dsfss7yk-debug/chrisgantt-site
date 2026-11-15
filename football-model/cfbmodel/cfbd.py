"""Season-level team inputs from the CollegeFootballData API (api.collegefootballdata.com).

The API key is not in the code: the session's network proxy adds it to requests for that host.
Without it (or offline with no cache) every input here is left neutral and the model runs as before.
The free tier allows 1000 calls a month; each season/endpoint is one call, cached in data/raw/cfb/cfbd
and refreshed for the current season at most once a day.

Per team-season, all known before the season's first game:
  talent      247 roster talent composite (2015+)
  returning   share of last season's offensive production (PPA) coming back
  recruit     recruiting points, average of the last four classes (the roster's composition)
  portal_net  transfer portal: summed player ratings in minus out
  new_coach   1 if the head coach is new this season
  prior_sp    last season's SP+ rating (from the coaches' season records)
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from cfbmodel import data
from nflmodel.data import _fetch

API = "https://api.collegefootballdata.com"
CACHE = data.RAW / "cfbd"
COLS = ["talent", "returning", "recruit", "portal_net", "new_coach", "prior_sp"]


def _get(endpoint: str, year: int):
    path = CACHE / f"{endpoint.replace('/', '_')}_{year}.json"
    refresh = year >= data.current_season() and _stale(path)
    try:
        p = _fetch(f"{API}/{endpoint}?year={year}", path, refresh=refresh)
    except RuntimeError as e:
        print(f"note: CollegeFootballData {endpoint} {year} unavailable ({e}); left neutral")
        return []
    if p is None:
        return []
    try:
        return json.loads(p.read_text())
    except ValueError:
        p.unlink(missing_ok=True)
        return []


def _stale(path) -> bool:
    return not path.exists() or time.time() - path.stat().st_mtime > 24 * 3600


def team_seasons(first: int, last: int) -> pd.DataFrame:
    """One row per (team name, season) with COLS."""
    rows = {}

    def put(team, season, col, val):
        rows.setdefault((team, season), {})[col] = val

    recruit = {}
    for y in range(first - 4, last + 1):
        for r in _get("recruiting/teams", y):
            recruit[(r["team"], y)] = r["points"]
    coach_by = {}   # (team, year) -> main coach id
    sp_by = {}
    for y in range(first - 1, last + 1):
        best = {}
        for c in _get("coaches", y):
            for s in c["seasons"]:
                if s["year"] != y:
                    continue
                g = s.get("games") or 0
                if s["school"] not in best or g > best[s["school"]][0]:
                    best[s["school"]] = (g, c["id"], c.get("hireDate"))
                if s.get("spOverall") is not None:
                    sp_by[(s["school"], y)] = s["spOverall"]
        for team, (_, cid, hired) in best.items():
            coach_by[(team, y)] = (cid, hired)

    for y in range(first, last + 1):
        for t in _get("talent", y):
            put(t["team"], y, "talent", t["talent"])
        for t in _get("player/returning", y):
            put(t["team"], y, "returning", t["percentPPA"])
        net = {}
        for p in _get("player/portal", y):
            rating = p.get("rating")
            if rating is None:
                rating = {5: .98, 4: .92, 3: .86, 2: .80}.get(p.get("stars"), 0.0)
            if p.get("destination"):
                net[p["destination"]] = net.get(p["destination"], 0.0) + rating
            if p.get("origin"):
                net[p["origin"]] = net.get(p["origin"], 0.0) - rating
        for team, v in net.items():
            put(team, y, "portal_net", v)
        teams = {k[0] for k in recruit if k[1] == y} | {k[0] for k in coach_by if k[1] == y}
        for team in teams:
            classes = [recruit[(team, y - i)] for i in range(4) if (team, y - i) in recruit]
            if classes:
                put(team, y, "recruit", float(np.mean(classes)))
        for (team, yy), (cid, hired) in coach_by.items():
            if yy != y:
                continue
            prev = coach_by.get((team, y - 1))
            if prev is not None:
                put(team, y, "new_coach", float(prev[0] != cid))
        for (team, yy), sp in sp_by.items():
            if yy == y - 1:
                put(team, y, "prior_sp", sp)
    if not rows:
        return pd.DataFrame(columns=["team", "season"] + COLS)
    out = pd.DataFrame([{"team": k[0], "season": k[1], **v} for k, v in rows.items()])
    for c in COLS:
        if c not in out:
            out[c] = np.nan
    return out


def add(df: pd.DataFrame) -> pd.DataFrame:
    """Merge home_/away_ COLS plus *_diff (home minus away) onto the game frame.
    Missing values are neutral: the season's median for FBS, 0 for a new-coach flag."""
    ts = team_seasons(int(df["season"].min()), int(df["season"].max()))
    for side in ("home", "away"):
        m = ts.rename(columns={"team": f"{side}_team", **{c: f"{side}_{c}" for c in COLS}})
        df = df.merge(m, on=[f"{side}_team", "season"], how="left")
    for c in COLS:
        for side in ("home", "away"):
            col = f"{side}_{c}"
            if c == "new_coach":
                df[col] = df[col].fillna(0.0)
            else:
                # FCS teams and unlisted teams: the season's 10th percentile (weak roster), else median
                lo = df.groupby("season")[col].transform(lambda s: s.quantile(0.1))
                med = df.groupby("season")[col].transform("median")
                fcs = df[f"{side}_fcs"] == 1 if f"{side}_fcs" in df else False
                df[col] = df[col].fillna(lo.where(fcs, med)).fillna(0.0)
        df[f"{c}_diff"] = df[f"home_{c}"] - df[f"away_{c}"]
    # season inputs matter most before the ratings have games to learn from
    wk = (1 - df["week"].clip(1, 10) / 10).clip(0, 1) if "week" in df else 0
    for c in ("talent", "returning", "recruit", "portal_net", "prior_sp"):
        df[f"{c}_early_diff"] = df[f"{c}_diff"] * wk
    return df
