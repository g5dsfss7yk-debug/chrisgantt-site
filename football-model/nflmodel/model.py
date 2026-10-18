"""Fit, backtest and predict.

Two ridge regressions on standardized features:
  margin model -> predicted home margin (the model's spread); win prob = Phi(margin / sigma)
  total model  -> predicted combined points

By default the total model takes the Vegas total as an input and learns how far to move
off it: on its own it lost to the market badly in 2026 (31-49 O/U), while anchored to the
line it went 41-39 and 52.7% over 2015-2025. The margin model stays independent.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MARGIN_FEATURES = [
    "elo_diff", "form_diff", "home_field", "div_game", "rest_diff",
    "home_off_bye", "away_off_bye", "home_short_week", "away_short_week",
    "travel_diff", "away_tz_east", "body_clock_early",
    "qb_val_diff", "qb_exp_diff", "home_backup_qb", "away_backup_qb",
    "inj_off_diff", "inj_def_diff",
    "away_dome_team_cold", "home_dome_team_cold",
    "epa_diff", "sr_diff", "to_diff", "luck_diff",
    "ret_off_diff", "ret_def_diff", "add_off_diff", "add_def_diff", "coach_tenure_diff",
    "home_new_qb", "away_new_qb", "elo_stale_diff", "epa_stale_diff",
    "nfelo_diff", "nfelo_qb_diff", "spread_move", "ref_margin",
]
TOTAL_FEATURES = [
    "off_sum", "def_sum", "league_pts", "dome", "cold", "heat", "high_wind", "wind", "turf",
    "rain", "snow", "gusty", "wet_wind",
    "div_game", "inj_off_sum", "inj_def_sum", "home_backup_qb", "away_backup_qb",
    "home_field", "epa_off_sum", "epa_def_sum", "sr_off_sum", "sr_def_sum",
    "form_stale_sum", "ret_off_sum", "stale_sum", "home_new_qb", "away_new_qb",
    "season_tot_sum", "ref_total",
]
FIRST_TRAIN_SEASON = 2012  # injury + snap-count data both exist from here


def _phi(x):
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2)))


def _ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=10.0))


class Model:
    def __init__(self, with_market: bool = False, market_totals: bool = True):
        self.with_market = with_market
        self.market_totals = market_totals or with_market
        self.mf = MARGIN_FEATURES + (["spread_line"] if with_market else [])
        self.tf = TOTAL_FEATURES + (["total_line"] if self.market_totals else [])

    def fit(self, df: pd.DataFrame) -> "Model":
        d = df.dropna(subset=["result"] + (["spread_line"] if self.with_market else []))
        self.margin = _ridge().fit(d[self.mf], d["result"])
        dt = d.dropna(subset=["total_line"]) if self.market_totals else d
        self.total = _ridge().fit(dt[self.tf], dt["total"])
        self.sigma = float(np.std(d["result"] - self.margin.predict(d[self.mf])))
        self.total_sigma = float(np.std(dt["total"] - self.total.predict(dt[self.tf])))
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["game_id", "season", "week", "gameday", "gametime", "away_team", "home_team",
                  "away_qb", "home_qb", "spread_line", "total_line",
                  "home_moneyline", "away_moneyline", "result", "total"]].copy()
        out["pred_margin"] = self.margin.predict(df[self.mf])
        out["pred_total"] = self.total.predict(df[self.tf])
        out["home_win_prob"] = _phi(out["pred_margin"] / self.sigma)
        return out

    def drivers(self, row: pd.Series, k: int = 4) -> list[tuple[str, float]]:
        """Top features pushing this game's predicted margin, in points."""
        sc, rg = self.margin.named_steps.values()
        z = (row[self.mf].astype(float).values - sc.mean_) / sc.scale_
        contrib = z * rg.coef_
        order = np.argsort(-np.abs(contrib))[:k]
        return [(self.mf[i], float(contrib[i])) for i in order]


def implied_prob(ml_home, ml_away):
    def p(ml):
        return np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100))
    ph, pa = p(ml_home), p(ml_away)
    return ph / (ph + pa)


def _ats(pred, line, actual, edge):
    """Against-the-spread record when the model disagrees with the line by >= edge."""
    m = np.abs(pred - line) >= edge
    side = np.sign(pred - line)[m]
    outcome = np.sign(actual - line)[m]
    wins, losses = int((side == outcome).sum()), int(((side == -outcome) & (outcome != 0)).sum())
    return wins, losses


def backtest(df: pd.DataFrame, seasons, with_market: bool = False) -> dict:
    preds = []
    for s in seasons:
        train = df[(df["season"] >= FIRST_TRAIN_SEASON) & (df["season"] < s)]
        test = df[(df["season"] == s) & df["result"].notna()]
        test = test.dropna(subset=["spread_line", "total_line"])
        preds.append(Model(with_market).fit(train).predict(test))
    p = pd.concat(preds, ignore_index=True)
    p = p[p["result"] != 0]
    y = (p["result"] > 0).astype(int)
    pr = p["home_win_prob"].clip(0.01, 0.99)
    vegas_p = _phi(p["spread_line"] / 13.5)
    res = {
        "games": len(p),
        "win_acc": float(((pr > 0.5) == y).mean()),
        "vegas_win_acc": float(((vegas_p > 0.5) == y).mean()),
        "log_loss": float(-np.mean(y * np.log(pr) + (1 - y) * np.log(1 - pr))),
        "vegas_log_loss": float(-np.mean(y * np.log(vegas_p) + (1 - y) * np.log(1 - vegas_p))),
        "brier": float(np.mean((pr - y) ** 2)),
        "vegas_brier": float(np.mean((vegas_p - y) ** 2)),
        "margin_mae": float(np.mean(np.abs(p["pred_margin"] - p["result"]))),
        "vegas_margin_mae": float(np.mean(np.abs(p["spread_line"] - p["result"]))),
        "total_mae": float(np.mean(np.abs(p["pred_total"] - p["total"]))),
        "vegas_total_mae": float(np.mean(np.abs(p["total_line"] - p["total"]))),
        "ats": {e: _ats(p["pred_margin"].values, p["spread_line"].values, p["result"].values, e)
                for e in (0, 1.5, 3, 4.5)},
        "ou": {e: _ats(p["pred_total"].values, p["total_line"].values, p["total"].values, e)
               for e in (0, 2, 4)},
        "by_season": p.assign(hit=((pr > 0.5) == y)).groupby("season")["hit"].mean().round(3).to_dict(),
    }
    return res
