"""Over/under player props (receptions, yards, attempts, passing) and first TD scorer.

For each market a gradient-boosted model predicts the player's expected stat from the
same inputs as the anytime-TD model plus his running averages and what the opponent
allows to his position. The chance of going over a line comes from what actually
happened to players with similar out-of-sample projections at the same position (an
empirical distribution), so the probabilities stay calibrated without assuming a shape.

There is no free archive of historical prop lines, so the backtest sets each line at the
player's running season average (books open close to it) and checks calibration and
hit rate against that.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from nflmodel import props

# market -> (stat column, positions that get the prop)
MARKETS = {
    "receptions": ("receptions", ("WR", "TE", "RB")),
    "receiving_yards": ("receiving_yards", ("WR", "TE", "RB")),
    "rush_attempts": ("carries", ("RB", "QB")),
    "rushing_yards": ("rushing_yards", ("RB", "QB")),
    "passing_yards": ("passing_yards", ("QB",)),
    "passing_tds": ("passing_tds", ("QB",)),
    "completions": ("completions", ("QB",)),
}
BINS = 25          # projection bins per position for the empirical distribution
MIN_GAMES = 1

BASE = ["carry_share", "target_share", "snap_pct", "touches", "rz_share", "implied_pts", "home",
        "games", "vacated_targets", "vacated_carries", "wind", "spread_for"]


def _features(stat: str) -> list[str]:
    avg = [f"avg_{c}" for c in props.STAT_COLS]
    opp = [c for c in ("opp_receptions_allowed", "opp_receiving_yards_allowed", "opp_rushing_yards_allowed",
                       "opp_passing_yards_allowed")]
    return BASE + avg + opp + ["is_rb", "is_wr", "is_te", "is_qb"]


def prepare(d: pd.DataFrame) -> pd.DataFrame:
    sign = np.where(d["home"] == 1, 1, -1)
    return d.assign(spread_for=sign * d["spread_line"])  # + = player's team favored


def _rows(d, market):
    stat, pos = MARKETS[market]
    return d[d["position"].isin(pos) & (d["games"] >= MIN_GAMES) & d["implied_pts"].notna()], stat


def _model(stat):
    loss = "poisson" if stat in ("receptions", "carries", "passing_tds", "completions") else "squared_error"
    return HistGradientBoostingRegressor(loss=loss, max_depth=4, learning_rate=0.05, max_iter=300,
                                         min_samples_leaf=100, random_state=0)


class StatModel:
    """Projection model plus an empirical outcome distribution for one market."""

    def __init__(self, market: str):
        self.market = market

    def fit(self, train: pd.DataFrame, history: pd.DataFrame):
        """train: rows to fit the projection; history: rows with out-of-sample projections
        (column 'proj') and actual results, used for the outcome distribution."""
        rows, stat = _rows(train, self.market)
        rows = rows[rows[stat].notna()]
        self.stat, self.feats = stat, _features(stat)
        self.m = _model(stat).fit(rows[self.feats].fillna(0), rows[stat].clip(lower=0) if stat != "rushing_yards"
                                  else rows[stat])
        self.dist = {}
        for pos, h in history.dropna(subset=["proj", stat]).groupby("position"):
            edges = np.unique(np.quantile(h["proj"], np.linspace(0, 1, BINS + 1)))
            idx = np.clip(np.searchsorted(edges, h["proj"], side="right") - 1, 0, len(edges) - 2)
            self.dist[pos] = (edges, [np.sort(h[stat].values[idx == i]) for i in range(len(edges) - 1)])
        return self

    def project(self, d: pd.DataFrame) -> pd.Series:
        return pd.Series(self.m.predict(d[self.feats].fillna(0)), index=d.index)

    def p_over(self, pos: str, proj: float, line: float) -> float:
        if pos not in self.dist:
            return np.nan
        edges, vals = self.dist[pos]
        i = int(np.clip(np.searchsorted(edges, proj, side="right") - 1, 0, len(vals) - 1))
        v = vals[i]
        return float((v > line).mean()) if len(v) else np.nan

    def median(self, pos: str, proj: float) -> float:
        edges, vals = self.dist[pos]
        i = int(np.clip(np.searchsorted(edges, proj, side="right") - 1, 0, len(vals) - 1))
        return float(np.median(vals[i]))


def walk_forward(d: pd.DataFrame, market: str, seasons) -> pd.DataFrame:
    """Out-of-sample projections and P(over the player's running average) per season."""
    d = prepare(d)
    rows, stat = _rows(d, market)
    rows = rows[rows[stat].notna()]
    first = min(seasons)
    # projections for the seasons before the test window seed the first distributions
    hist = []
    for s in range(first - 3, first):
        m = _model(stat).fit(rows.loc[rows["season"] < s, _features(stat)].fillna(0),
                             rows.loc[rows["season"] < s, stat])
        cur = rows[rows["season"] == s]
        hist.append(cur.assign(proj=m.predict(cur[_features(stat)].fillna(0))))
    out = []
    for s in seasons:
        sm = StatModel(market).fit(rows[rows["season"] < s], pd.concat(hist))
        test = rows[rows["season"] == s].copy()
        test["proj"] = sm.project(test)
        test["line"] = (np.floor(test[f"avg_{stat}"].fillna(0)) + 0.5)  # stand-in for the book's line
        test["p_over"] = [sm.p_over(p, x, l) for p, x, l in zip(test["position"], test["proj"], test["line"])]
        test["stat"] = stat
        out.append(test)
        hist.append(test[rows.columns.tolist() + ["proj"]])
    return pd.concat(out)


def first_td(today: pd.DataFrame) -> pd.Series:
    """Chance each player scores the game's first TD, from the anytime-TD probabilities.

    Each player's TD rate is lambda = -ln(1 - P(anytime)); the first TD goes to a player in
    proportion to his rate among everyone in the game. Players outside the list (defense,
    special teams, unlisted backups) take about 8% of first TDs, so the shares are scaled to 92%.
    """
    lam = -np.log1p(-today["p"].clip(upper=0.95))
    return lam / lam.groupby(today["game_id"]).transform("sum") * 0.92
