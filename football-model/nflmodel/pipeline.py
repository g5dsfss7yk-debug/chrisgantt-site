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


def load(refresh: bool = False, use_forecasts: bool = True) -> pd.DataFrame:
    seasons = range(model.FIRST_TRAIN_SEASON, data.current_season() + 1)
    snaps = data.load_snaps(seasons, refresh)
    return features.build(
        data.load_games(refresh),
        injuries=features.injury_scores(data.load_injuries(seasons, refresh), snaps),
        continuity=features.roster_continuity(snaps, data.load_rosters(seasons, refresh)),
        pbp=data.load_team_pbp(range(model.FIRST_TRAIN_SEASON - 1, data.current_season() + 1), refresh),
        weather_text=data.load_game_weather(seasons, refresh),
        nfelo=data.load_nfelo(refresh),
        forecasts=forecasts() if use_forecasts else None,
    )
