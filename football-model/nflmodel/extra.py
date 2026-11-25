"""Extra team ratings from nflverse's advanced data, for the spread, totals and props models.

- PFR advanced stats (2018+): pressure rate allowed by the offense and created by the
  defense, QB bad-throw rate, receiver drop rate, defensive missed-tackle rate.
- Next Gen Stats (2016+): QB completion % over expected, time to throw, aggressiveness;
  receivers' average separation; rushing yards over expected.
- Referee: the crew chief's earlier games, points vs the closing total and home margin vs
  the closing spread.

Every rating is a running average of the team's (or referee's) EARLIER games only
(exponentially weighted, carried across seasons), so a game never sees its own result.
Columns come back per game_id as home_*, away_*, *_diff (home minus away) and *_sum.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nflmodel import data, teams

EXTRA = data.RAW / "extra"
RELEASE = data.RELEASE
ALPHA = 0.2          # weight of the latest game in a running average
REF_MIN_GAMES = 16   # referee history needed before his tendency is used


def _get(name: str, url: str, live: bool = False):
    return data._fetch(url, EXTRA / name, refresh=False, live=live)


def _pfr(seasons) -> pd.DataFrame:
    rows = []
    cur = data.current_season()
    for s in seasons:
        if s < 2018:
            continue
        p = data._fetch(f"{RELEASE}/pfr_advstats/advstats_week_pass_{s}.csv", EXTRA / f"pass_{s}.csv",
                        live=s == cur)
        d = data._fetch(f"{RELEASE}/pfr_advstats/advstats_week_def_{s}.csv", EXTRA / f"def_{s}.csv",
                        live=s == cur)
        if p is None or d is None:
            continue
        p, d = pd.read_csv(p, low_memory=False), pd.read_csv(d, low_memory=False)
        off = p.groupby(["game_id", "team"]).agg(pressured=("times_pressured", "sum"),
                                                 bad=("passing_bad_throws", "sum"),
                                                 drops=("passing_drops", "sum")).reset_index()
        de = d.groupby(["game_id", "team"]).agg(pressures=("def_pressures", "sum"),
                                                missed=("def_missed_tackles", "sum"),
                                                tackles=("def_tackles_combined", "sum")).reset_index()
        rows.append(off.merge(de, on=["game_id", "team"], how="outer"))
    return pd.concat(rows) if rows else pd.DataFrame()


def _ngs() -> pd.DataFrame:
    out = []
    for kind in ("passing", "receiving", "rushing"):
        f = data._fetch(f"{RELEASE}/nextgen_stats/ngs_{kind}.csv.gz", EXTRA / f"ngs_{kind}.csv.gz", live=True)
        if f is None:
            continue
        x = pd.read_csv(f, low_memory=False)
        x = x[(x["week"] > 0) & (x["season_type"] == "REG")]
        x["team"] = x["team_abbr"].map(teams.franchise)
        if kind == "passing":
            w = x["attempts"]
            g = x.assign(cpoe=x["completion_percentage_above_expectation"] * w, ttt=x["avg_time_to_throw"] * w,
                         aggr=x["aggressiveness"] * w, w=w)
            g = g.groupby(["season", "week", "team"])[["cpoe", "ttt", "aggr", "w"]].sum()
            out.append(g[["cpoe", "ttt", "aggr"]].div(g["w"], axis=0))
        elif kind == "receiving":
            w = x["targets"]
            g = x.assign(sep=x["avg_separation"] * w, yacoe=x["avg_yac_above_expectation"] * w, w=w)
            g = g.groupby(["season", "week", "team"])[["sep", "yacoe", "w"]].sum()
            out.append(g[["sep", "yacoe"]].div(g["w"], axis=0))
        else:
            w = x["rush_attempts"]
            g = x.assign(ryoe=x["rush_yards_over_expected_per_att"] * w, w=w)
            g = g.groupby(["season", "week", "team"])[["ryoe", "w"]].sum()
            out.append(g[["ryoe"]].div(g["w"], axis=0))
    return pd.concat(out, axis=1).reset_index() if out else pd.DataFrame()


def _running(long: pd.DataFrame, cols) -> pd.DataFrame:
    """Per team, the running average of cols over earlier games (shifted one game)."""
    long = long.sort_values(["team", "gameday"])
    g = long.groupby("team")[cols]
    prior = g.transform(lambda s: s.shift(1).ewm(alpha=ALPHA, ignore_na=True).mean())
    return long[["game_id", "team"]].join(prior)


def build(games: pd.DataFrame, team_pbp: pd.DataFrame) -> pd.DataFrame:
    """games: nflverse schedule; team_pbp: data.load_team_pbp (dropbacks, plays per team-game)."""
    g = games[["game_id", "season", "week", "gameday", "home_team", "away_team", "result", "total",
               "spread_line", "total_line", "referee"]].copy()
    g["gameday"] = pd.to_datetime(g["gameday"])
    long = pd.concat([
        g.assign(team=g["home_team"], opp=g["away_team"]),
        g.assign(team=g["away_team"], opp=g["home_team"]),
    ])[["game_id", "season", "week", "gameday", "team", "opp"]]
    for c in ("team", "opp"):
        long[c] = long[c].map(teams.franchise)

    tp = team_pbp[["game_id", "team", "dropbacks"]].copy()
    tp["team"] = tp["team"].map(teams.franchise)
    long = long.merge(tp, on=["game_id", "team"], how="left")
    opp_db = tp.rename(columns={"team": "opp", "dropbacks": "opp_dropbacks"})
    long = long.merge(opp_db, on=["game_id", "opp"], how="left")

    pfr = _pfr(range(2018, data.current_season() + 1))
    if len(pfr):
        pfr["team"] = pfr["team"].map(teams.franchise)
        long = long.merge(pfr, on=["game_id", "team"], how="left")
        long["pressure_allowed"] = long["pressured"] / long["dropbacks"]
        long["pressure_made"] = long["pressures"] / long["opp_dropbacks"]
        long["bad_throw"] = long["bad"] / long["dropbacks"]
        long["drop_rate"] = long["drops"] / long["dropbacks"]
        long["missed_tackle"] = long["missed"] / (long["missed"] + long["tackles"])
    ngs = _ngs()
    if len(ngs):
        long = long.merge(ngs, on=["season", "week", "team"], how="left")
    cols = [c for c in ("pressure_allowed", "pressure_made", "bad_throw", "drop_rate", "missed_tackle",
                        "cpoe", "ttt", "aggr", "sep", "yacoe", "ryoe") if c in long]
    # a game with no data yet (upcoming) keeps NaN for its own stat but still gets the prior average
    run = _running(long, cols)

    out = g[["game_id"]].copy()
    h = run.rename(columns={c: f"home_x_{c}" for c in cols}).rename(columns={"team": "home_f"})
    a = run.rename(columns={c: f"away_x_{c}" for c in cols}).rename(columns={"team": "away_f"})
    out = out.assign(home_f=g["home_team"].map(teams.franchise), away_f=g["away_team"].map(teams.franchise))
    out = out.merge(h, on=["game_id", "home_f"], how="left").merge(a, on=["game_id", "away_f"], how="left")
    for c in cols:
        out[f"x_{c}_diff"] = out[f"home_x_{c}"] - out[f"away_x_{c}"]
        out[f"x_{c}_sum"] = out[f"home_x_{c}"] + out[f"away_x_{c}"]
    if "pressure_allowed" in cols:
        # pass-rush matchups: each offense's pressure allowed against the other defense's pressure rate
        out["x_pressure_matchup_diff"] = ((out["away_x_pressure_made"] + out["home_x_pressure_allowed"])
                                          - (out["home_x_pressure_made"] + out["away_x_pressure_allowed"]))

    # Referee: crew chief's earlier games
    r = g.sort_values("gameday").copy()
    r["over"] = r["total"] - r["total_line"]
    r["home_ats"] = r["result"] - r["spread_line"]
    grp = r.groupby("referee")
    for col, name in (("over", "x_ref_over"), ("home_ats", "x_ref_home")):
        prev = grp[col].transform(lambda s: s.shift(1).expanding().mean())
        n = grp[col].transform(lambda s: s.shift(1).expanding().count())
        r[name] = np.where(n >= REF_MIN_GAMES, prev, np.nan)
    out = out.merge(r[["game_id", "x_ref_over", "x_ref_home"]], on="game_id", how="left")
    return out.drop(columns=["home_f", "away_f"])


SPREAD_EXTRA = ["x_pressure_allowed_diff", "x_pressure_made_diff", "x_pressure_matchup_diff", "x_bad_throw_diff",
                "x_drop_rate_diff", "x_missed_tackle_diff", "x_cpoe_diff", "x_ttt_diff", "x_aggr_diff",
                "x_sep_diff", "x_yacoe_diff", "x_ryoe_diff", "x_ref_home"]
TOTAL_EXTRA = ["x_pressure_allowed_sum", "x_pressure_made_sum", "x_bad_throw_sum", "x_missed_tackle_sum",
               "x_cpoe_sum", "x_ttt_sum", "x_aggr_sum", "x_sep_sum", "x_yacoe_sum", "x_ryoe_sum", "x_ref_over"]
