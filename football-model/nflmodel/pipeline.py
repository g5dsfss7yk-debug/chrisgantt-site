"""Download everything and build the feature table."""
from __future__ import annotations

import pandas as pd

from . import data, features, model


def forecasts() -> dict:
    """Weather job forecasts -> {game_id: {temp, wind, gust, rain, snow}} (rain/snow 0, 0.5, 1)."""
    out = {}
    for f in data.load_forecasts().itertuples(index=False):
        p = f.precip_prob if pd.notna(f.precip_prob) else 0
        wet = 1.0 if p >= 60 and f.precip_in >= 0.05 else (0.5 if p >= 35 else 0.0)
        snowy = f.snow_in >= 0.1
        out[f.game_id] = {"temp": f.temp, "wind": f.wind, "gust": f.gust,
                          "rain": 0.0 if snowy else wet, "snow": max(wet, 0.5) if snowy else 0.0}
    return out


def starters(games: pd.DataFrame, qbs: dict[str, str], season: int, week: int) -> pd.DataFrame:
    """Replace the schedule's listed QB with the confirmed starter, e.g. {"PHI": "Tanner McKee"}.

    The schedule file keeps the preseason starter until it is updated, so an injured QB can
    still be listed on game day. Player ids come from weekly player stats.
    """
    if not qbs:
        return games
    from nflmodel import props
    pg = props.load_player_games()
    games = games.copy()
    for team, name in qbs.items():
        hit = pg[pg["player_display_name"].str.lower() == name.lower()]
        if hit.empty:
            # No NFL stats yet (rookie / first start): take the id from the depth chart, and the
            # model rates him as a QB with no history.
            from nflmodel import lineups
            dc = lineups.load_depth(season)
            dc = dc[dc["player_name"].str.lower() == name.lower()]
            if dc.empty:
                raise SystemExit(f"no player named {name!r} in the weekly stats or depth chart")
            hit = pd.DataFrame({"player_id": [dc["gsis_id"].iloc[0]], "player_display_name": [dc["player_name"].iloc[0]]})
            print(f"note: {name} has no NFL stats; rated as a QB with no history")
        pid = hit["player_id"].iloc[-1]
        for side in ("home", "away"):
            m = (games["season"] == season) & (games["week"] == week) & (games[f"{side}_team"] == team)
            games.loc[m, [f"{side}_qb_id", f"{side}_qb_name"]] = [pid, hit["player_display_name"].iloc[-1]]
    return games


def load(refresh: bool = False, use_forecasts: bool = True, qbs: dict | None = None,
         season: int | None = None, week: int | None = None) -> pd.DataFrame:
    seasons = range(model.FIRST_TRAIN_SEASON, data.current_season() + 1)
    snaps = data.load_snaps(seasons, refresh)
    pbp = data.load_team_pbp(range(model.FIRST_TRAIN_SEASON - 1, data.current_season() + 1), refresh)
    df = features.build(
        starters(data.load_games(refresh), qbs or {}, season, week),
        injuries=features.injury_scores(data.load_injuries(seasons, refresh), snaps),
        continuity=features.roster_continuity(snaps, data.load_rosters(seasons, refresh)),
        pbp=pbp,
        weather_text=data.load_game_weather(seasons, refresh),
        nfelo=data.load_nfelo(refresh),
        forecasts=forecasts() if use_forecasts else None,
    )
    return add_extra(df, data.load_games(refresh), pbp)


def add_extra(df: pd.DataFrame, games: pd.DataFrame, pbp: pd.DataFrame) -> pd.DataFrame:
    """Pressure, Next Gen and referee ratings (nflmodel.extra). Seasons before the data starts
    (PFR 2018, NGS 2016) get neutral values: 0 for a home-minus-away difference, the first
    available seasons' median for a sum."""
    from nflmodel import extra
    x = extra.build(games, pbp)
    df = df.merge(x, on="game_id", how="left")
    for c in [c for c in x.columns if c.startswith("x_")]:
        if c.endswith("_diff") or c == "x_ref_home":
            df[c] = df[c].fillna(0.0)
        else:
            first = df.loc[df[c].notna(), "season"].min()
            df[c] = df[c].fillna(df.loc[df["season"].between(first, first + 1), c].median())
    return df
