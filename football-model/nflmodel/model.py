"""Two-stage models: rate the game, then judge it against the betting line.

Stage 1 (rating): ridge regression from football features to the home margin / game
total, never looking at a betting line.

Stage 2 (edge): the market is usually right, so the gap between the rating and the line
is only partly real. A logistic regression, fit on out-of-sample stage-1 ratings from
earlier seasons, maps (rating - line) to the probability the bet wins. These
probabilities are calibrated: a 56% pick has historically won about 56% of the time.

Spreads are judged against the *opening* line using only information known when lines
open (OPEN_FEATURES). Totals are judged against the closing total on game day, when the
weather forecast and injury report are in (CLOSE_TOTAL_FEATURES).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Known when lines open, early in the week.
OPEN_FEATURES = [
    "elo_diff", "nfelo_diff", "nfelo_qb_diff", "form_diff", "epa_diff", "sr_diff",
    "to_diff", "luck_diff", "qb_val_diff", "qb_exp_diff", "home_new_qb", "away_new_qb",
    "ret_off_diff", "ret_def_diff", "add_off_diff", "add_def_diff", "coach_tenure_diff",
    "elo_stale_diff", "epa_stale_diff",
    "home_field", "div_game", "rest_diff", "home_off_bye", "away_off_bye",
    "home_short_week", "away_short_week", "travel", "away_tz_east", "body_clock_early",
]
# Known only on game day.
LATE_FEATURES = ["inj_off_diff", "inj_def_diff", "home_backup_qb", "away_backup_qb",
                 "away_dome_team_cold", "home_dome_team_cold"]
CLOSE_TOTAL_FEATURES = [
    "off_sum", "def_sum", "league_pts", "epa_off_sum", "epa_def_sum", "sr_off_sum", "sr_def_sum",
    "season_tot_sum", "stale_sum", "home_new_qb", "away_new_qb", "home_backup_qb", "away_backup_qb",
    "inj_off_sum", "inj_def_sum", "div_game", "home_field",
    "dome", "cold", "heat", "wind", "high_wind", "gusty", "rain", "snow", "wet_wind", "turf",
]
FIRST_TRAIN_SEASON = 2009   # injury reports and nfelo opening lines start here
MIN_STAGE2_SEASONS = 2


def _ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=10.0))


class Market:
    """Stage 1 + stage 2 for one bet type.

    kind="spread": target = home margin, P = home covers.
    kind="total":  target = combined points, P = over.
    """

    def __init__(self, kind: str, features: list[str], line: str):
        self.kind, self.features, self.line = kind, features, line
        self.target = "result" if kind == "spread" else "total"

    def _rating_fit(self, d):
        return _ridge().fit(d[self.features], d[self.target])

    def _oos_ratings(self, d):
        """Stage-1 ratings for each training season from a model fit on earlier seasons only."""
        out = pd.Series(np.nan, index=d.index)
        seasons = sorted(d["season"].unique())
        for s in seasons[MIN_STAGE2_SEASONS:]:
            past = d[d["season"] < s]
            cur = d["season"] == s
            out[cur] = self._rating_fit(past).predict(d.loc[cur, self.features])
        return out

    def _x2(self, rating, line):
        rating, line = np.asarray(rating, float), np.asarray(line, float)
        return (rating - line).reshape(-1, 1)

    def fit(self, df: pd.DataFrame) -> "Market":
        d = df[df["result"].notna() & (df["season"] >= FIRST_TRAIN_SEASON)]
        self.rating = self._rating_fit(d)
        oos = self._oos_ratings(d)
        e = d.assign(r=oos).dropna(subset=["r", self.line])
        diff = e[self.target] - e[self.line]
        e, diff = e[diff != 0], diff[diff != 0]  # pushes carry no information
        self.edge = LogisticRegression(C=1.0).fit(self._x2(e["r"], e[self.line]), (diff > 0).astype(int))
        self.rating_sd = float(np.std(d[self.target] - self.rating.predict(d[self.features])))
        return self

    def predict(self, df: pd.DataFrame, line: pd.Series | None = None) -> pd.DataFrame:
        line = df[self.line] if line is None else line
        rating = self.rating.predict(df[self.features])
        ok = line.notna().values
        p = np.full(len(df), np.nan)
        if ok.any():
            p[ok] = self.edge.predict_proba(self._x2(rating[ok], line[ok]))[:, 1]
        return pd.DataFrame({"rating": rating, "line": line.values, "p": p}, index=df.index)

    def drivers(self, row: pd.Series, k: int = 4) -> list[tuple[str, float]]:
        sc, rg = self.rating.named_steps.values()
        contrib = (row[self.features].astype(float).values - sc.mean_) / sc.scale_ * rg.coef_
        return [(self.features[i], float(contrib[i])) for i in np.argsort(-np.abs(contrib))[:k]]


def spread_market() -> Market:
    return Market("spread", OPEN_FEATURES, "spread_open")


def total_market() -> Market:
    return Market("total", CLOSE_TOTAL_FEATURES, "total_line")


# --- evaluation ---------------------------------------------------------------------
def walk_forward(df: pd.DataFrame, make, seasons) -> pd.DataFrame:
    """Out-of-sample predictions: each season predicted by a model fit on earlier seasons."""
    out = []
    for s in seasons:
        m = make().fit(df[df["season"] < s])
        test = df[(df["season"] == s) & df["result"].notna()]
        out.append(pd.concat([test, m.predict(test)], axis=1))
    return pd.concat(out)


def record(p: pd.DataFrame, target: str, threshold: float) -> dict:
    """Bets where P(win) >= threshold on either side, graded against p['line']."""
    d = p.dropna(subset=["p", "line"])
    side = np.where(d["p"] >= 0.5, 1, -1)
    conf = np.maximum(d["p"], 1 - d["p"])
    outcome = np.sign(d[target] - d["line"])
    bet = (conf >= threshold) & (outcome != 0)
    wins = int(((side == outcome) & bet).sum())
    n = int(bet.sum())
    return {"bets": n, "wins": wins, "rate": wins / n if n else float("nan"),
            "roi": (wins * 100 / 110 - (n - wins)) / n if n else float("nan")}


def calibration(p: pd.DataFrame, target: str) -> pd.DataFrame:
    """Predicted vs actual win rate of the favored side, by confidence bucket."""
    d = p.dropna(subset=["p", "line"])
    d = d[np.sign(d[target] - d["line"]) != 0]
    conf = np.maximum(d["p"], 1 - d["p"])
    won = np.where(d["p"] >= 0.5, d[target] > d["line"], d[target] < d["line"])
    b = pd.cut(conf, [0.5, 0.52, 0.54, 0.56, 0.58, 0.6, 1.0])
    return pd.DataFrame({"predicted": conf, "actual": won}).groupby(b, observed=True).agg(
        n=("actual", "size"), predicted=("predicted", "mean"), actual=("actual", "mean")).round(3)
