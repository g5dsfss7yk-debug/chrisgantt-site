"""Game-day lineups: who starts, and which regulars are missing.

Sources: nflverse's daily ESPN depth chart (current season) for the starters at every
position, the official injury report for Out/Doubtful, and snap counts for each player's
recent role. A "regular" is anyone who played at least REGULAR_PCT of his unit's snaps in
the team's last two games; a regular is missing if he is Out/Doubtful or no longer on the
depth chart (IR, released, suspended).
"""
from __future__ import annotations

import pandas as pd

from nflmodel import data

REGULAR_PCT = 0.5
UNITS = {"QB": "QB", "RB": "skill", "FB": "skill", "WR": "skill", "TE": "skill",
         "T": "OL", "G": "OL", "C": "OL", "OL": "OL",
         "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "OLB": "LB", "ILB": "LB", "MLB": "LB", "LB": "LB",
         "CB": "DB", "S": "DB", "SS": "DB", "FS": "DB", "DB": "DB"}


def load_depth(season: int, refresh: bool = False) -> pd.DataFrame:
    """Latest daily depth-chart snapshot for the season (one row per team, slot, rank)."""
    path = data._fetch(f"{data.RELEASE}/depth_charts/depth_charts_{season}.csv",
                       data.RAW / "depth_charts" / f"{season}.csv", refresh, live=True)
    d = pd.read_csv(path, low_memory=False)
    if "dt" not in d:
        raise SystemExit(f"depth chart for {season} is in the old weekly format; lineups need the daily one")
    return d[d["dt"] == d["dt"].max()]


def _norm(name: pd.Series) -> pd.Series:
    return name.str.lower().str.replace(r"[^a-z ]", "", regex=True).str.replace(r"\s+(jr|sr|ii|iii|iv)$", "", regex=True)


def report(team: str, season: int, week: int, refresh: bool = False) -> dict:
    """Starters by position and the regulars who won't play."""
    depth = load_depth(season, refresh)
    depth = depth[depth["team"] == team]
    starters = (depth[depth["pos_rank"] == 1].drop_duplicates("gsis_id")
                [["pos_abb", "player_name", "gsis_id", "pos_grp"]])
    inj = data.load_injuries([season], refresh)
    inj = inj[(inj["team"] == team) & (inj["week"] == week)]
    out_ids = set(inj.loc[inj["report_status"].isin(["Out", "Doubtful"]), "gsis_id"])
    questionable = inj.loc[inj["report_status"] == "Questionable", "full_name"].tolist()

    snaps = data.load_snaps([season], refresh)
    snaps = snaps[(snaps["team"] == team) & (snaps["week"] < week)]
    recent = snaps[snaps["week"] >= snaps["week"].nlargest(2).min()] if len(snaps) else snaps
    recent = recent.assign(pct=recent[["offense_pct", "defense_pct"]].max(axis=1))
    regulars = recent.groupby(["player", "position"])["pct"].mean().reset_index()
    regulars = regulars[regulars["pct"] >= REGULAR_PCT]

    on_chart = set(_norm(depth["player_name"]))
    out_names = set(_norm(inj.loc[inj["gsis_id"].isin(out_ids), "full_name"]))
    regulars["key"] = _norm(regulars["player"])
    regulars["status"] = ["Out/Doubtful" if k in out_names else ("off depth chart" if k not in on_chart else "")
                          for k in regulars["key"]]
    missing = regulars[regulars["status"] != ""].assign(unit=lambda x: x["position"].map(UNITS).fillna("other"))
    starters = starters.assign(out=starters["gsis_id"].isin(out_ids))
    return {"starters": starters, "missing": missing.sort_values("pct", ascending=False),
            "questionable": questionable, "out_ids": out_ids, "depth": depth}


def skill_players(depth: pd.DataFrame, max_rank: int = 3) -> pd.DataFrame:
    """RB/WR/TE/QB on the offensive depth chart, for props."""
    d = depth[depth["pos_abb"].isin(["QB", "RB", "WR", "TE"]) & (depth["pos_rank"] <= max_rank)
              & ~depth["pos_grp"].str.contains("Special", na=False)]
    return d.drop_duplicates("gsis_id")[["gsis_id", "player_name", "pos_abb"]]


MISS_UNITS = ("QB", "OL", "skill", "DL", "LB", "DB")


def missing_from_snaps(snaps: pd.DataFrame) -> pd.DataFrame:
    """For every past team-game: snap share of the regulars from the team's previous two
    games who did not play, summed by unit (a starter who played 90% counts 0.9).

    This sees every absence, including IR, suspensions and scratches that never appear
    on the injury report. Columns: game_id, team, miss_<unit>, miss_total.
    """
    s = snaps[snaps["game_type"] == "REG"].copy()
    s["pct"] = s[["offense_pct", "defense_pct"]].max(axis=1)
    s["unit"] = s["position"].map(UNITS)
    s = s[s["unit"].isin(MISS_UNITS)]
    games = s.drop_duplicates(["season", "week", "team"])[["season", "week", "team", "game_id"]].sort_values(
        ["team", "season", "week"])
    out = []
    for team, tg in games.groupby("team"):
        ts = s[s["team"] == team]
        by_game = {g: grp for g, grp in ts.groupby("game_id")}
        order = list(tg.itertuples(index=False))
        for i, g in enumerate(order):
            prev = [p for p in order[max(0, i - 2):i] if p.season == g.season]
            row = {"game_id": g.game_id, "team": team, **{f"miss_{u}": 0.0 for u in MISS_UNITS}}
            if prev:
                hist = pd.concat([by_game[p.game_id] for p in prev])
                reg = hist.groupby(["pfr_player_id", "unit"])["pct"].sum() / len(prev)
                reg = reg[reg >= REGULAR_PCT].reset_index()
                played = set(by_game[g.game_id].loc[by_game[g.game_id]["pct"] > 0, "pfr_player_id"])
                gone = reg[~reg["pfr_player_id"].isin(played)]
                for u, v in gone.groupby("unit")["pct"].sum().items():
                    row[f"miss_{u}"] = v
            out.append(row)
    d = pd.DataFrame(out)
    d["miss_total"] = d[[f"miss_{u}" for u in MISS_UNITS]].sum(axis=1)
    return d


def missing_now(team: str, season: int, week: int, refresh: bool = False) -> dict:
    """The same measure for an upcoming game, from the injury report and depth chart."""
    m = report(team, season, week, refresh)["missing"]
    row = {f"miss_{u}": float(m.loc[m["unit"] == u, "pct"].sum()) for u in MISS_UNITS}
    row["miss_total"] = sum(row.values())
    return row
