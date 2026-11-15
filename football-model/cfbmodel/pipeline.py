from __future__ import annotations

import numpy as np
import pandas as pd

from cfbmodel import data, features

VENUES = data.ROOT / "scripts" / "cfb_venues.csv"


def _travel(games: pd.DataFrame) -> pd.DataFrame:
    """Field and travel from stadium coordinates: turf (1 turf, 0 grass, 0.5 unknown), dome,
    the away team's miles from its home stadium and time zones crossed (east is +), and the
    same for the home team at a neutral site."""
    v = pd.read_csv(VENUES).set_index("venue_id")
    g = games[["game_id", "venue_id", "home_id", "away_id", "neutral_site"]].copy()
    home_games = g[~g["neutral_site"].astype(bool) & g["venue_id"].notna()]
    home_venue = home_games.groupby("home_id")["venue_id"].agg(lambda s: s.value_counts().index[0])
    lat, lon = v["latitude"], v["longitude"]

    def miles(a, b):
        la1, lo1, la2, lo2 = (np.radians(x) for x in (lat.reindex(a).values, lon.reindex(a).values,
                                                       lat.reindex(b).values, lon.reindex(b).values))
        h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
        return 3959 * 2 * np.arcsin(np.sqrt(h))

    out = g[["game_id"]].copy()
    for side in ("away", "home"):
        base = g[f"{side}_id"].map(home_venue)
        out[f"{side}_miles"] = miles(base, g["venue_id"])
        out[f"{side}_tz"] = (lon.reindex(g["venue_id"]).values - lon.reindex(base).values) / 15
    out["home_miles"] = np.where(g["neutral_site"].astype(bool), out["home_miles"], 0.0)
    out["home_tz"] = np.where(g["neutral_site"].astype(bool), out["home_tz"], 0.0)
    grass = v["grass"].map({True: 0.0, False: 1.0, "True": 0.0, "False": 1.0})
    out["turf"] = g["venue_id"].map(grass).fillna(0.5).values
    out["dome"] = g["venue_id"].map(v["dome"].astype(float)).fillna(0).values
    out["travel_diff"] = (out["away_miles"].fillna(0) - out["home_miles"].fillna(0)) / 1000
    out["tz_diff"] = out["away_tz"].fillna(0).abs() - out["home_tz"].fillna(0).abs()
    return out


def load(refresh: bool = False):
    games = data.load_schedules(refresh)
    team_games = data.load_team_games(refresh)
    df = features.build(games, team_games, data.load_lines(refresh))
    df = df.merge(_travel(games), on="game_id", how="left")
    # FCS-only games update ratings but are not rated or bet
    return df[(df["home_fcs"] == 0) | (df["away_fcs"] == 0)].reset_index(drop=True)
