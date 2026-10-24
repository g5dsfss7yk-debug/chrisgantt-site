from __future__ import annotations

from cfbmodel import data, features


def load(refresh: bool = False):
    games = data.load_schedules(refresh)
    team_games = data.load_team_games(refresh)
    df = features.build(games, team_games, data.load_lines(refresh))
    # FCS-only games update ratings but are not rated or bet
    return df[(df["home_fcs"] == 0) | (df["away_fcs"] == 0)].reset_index(drop=True)
