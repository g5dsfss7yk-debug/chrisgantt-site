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
            raise SystemExit(f"no player named {name!r} in the weekly stats")
        pid = hit["player_id"].iloc[-1]
        for side in ("home", "away"):
            m = (games["season"] == season) & (games["week"] == week) & (games[f"{side}_team"] == team)
            games.loc[m, [f"{side}_qb_id", f"{side}_qb_name"]] = [pid, hit["player_display_name"].iloc[-1]]
    return games


def load(refresh: bool = False, use_forecasts: bool = True, qbs: dict | None = None,
         season: int | None = None, week: int | None = None) -> pd.DataFrame:
    seasons = range(model.FIRST_TRAIN_SEASON, data.current_season() + 1)
    snaps = data.load_snaps(seasons, refresh)
    return features.build(
        starters(data.load_games(refresh), qbs or {}, season, week),
        injuries=features.injury_scores(data.load_injuries(seasons, refresh), snaps),
        continuity=features.roster_continuity(snaps, data.load_rosters(seasons, refresh)),
        pbp=data.load_team_pbp(range(model.FIRST_TRAIN_SEASON - 1, data.current_season() + 1), refresh),
        weather_text=data.load_game_weather(seasons, refresh),
        nfelo=data.load_nfelo(refresh),
        forecasts=forecasts() if use_forecasts else None,
    )
