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
    # field (Nov 2026): STRONG vs the opener 52.6% -> 54.7% (2018-21), flat in 2022-25
    "turf", "dome",
]
# Travel distance, time zones crossed and turf were tested for the spread and not kept:
# STRONG 56.1% -> 54.8% (2018-21), 62.5% -> 65.6% (2022-25), 40.7% -> 38.5% (2026).


def spread_market(line: str = "spread_open") -> Market:
    return Market("spread", SPREAD_FEATURES, line)


def total_market(line: str = "total_open") -> Market:
    return Market("total", TOTAL_FEATURES, line, center_on="line")
# CollegeFootballData season inputs (cfbmodel/cfbd.py: talent, returning production, recruiting,
# portal, new coach, prior SP+) were tested Nov 2026 and NOT used. They cut margin error
# (12.98 -> 12.76, 12.66 -> 12.55) but STRONG fell in both periods: all season 56.1% -> 51.9%
# (2018-21), 62.5% -> 57.6% (2022-25); early-season weighted 53.2% / 59.8%; the market already
# prices them. Totals with returning production and coach changes: flat (55.1% / 48.4%).
# They are shown on the card as a roster line instead.
