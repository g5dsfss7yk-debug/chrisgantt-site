"""College spread and total markets on the same two-stage ensemble as the NFL model."""
from __future__ import annotations

from nflmodel.model import Market

SPREAD_FEATURES = [
    "elo_diff", "pts_diff", "ppg_diff", "epa_diff", "sr_diff", "exp_diff", "havoc_diff", "sack_diff",
    "rz_diff", "st_diff", "to_diff", "home_field", "conf_game", "rest_diff", "home_off_bye", "away_off_bye",
    "fcs_diff", "early_season", "home_qb_change", "away_qb_change", "home_new_qb", "away_new_qb", "postseason",
]
TOTAL_FEATURES = [
    "plays_sum", "pass_sum", "epa_off_sum", "epa_def_sum", "sr_off_sum", "sr_def_sum", "exp_off_sum",
    "exp_def_sum", "ppg_off_sum", "ppg_def_sum", "rz_off_sum", "rz_def_sum", "havoc_sum", "home_field",
    "conf_game", "early_season", "postseason", "home_qb_change", "away_qb_change",
]


def spread_market(line: str = "spread_open") -> Market:
    return Market("spread", SPREAD_FEATURES, line)


def total_market(line: str = "total_open") -> Market:
    return Market("total", TOTAL_FEATURES, line)
