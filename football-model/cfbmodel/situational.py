"""College totals from situations only (audit H, audit/market_error_model.py cfb).

Predicts whether a game goes over the closing total from situational inputs (no team strength):
line and total movement, rest, QB change/new QB, last margin, travel, neutral site, conference,
FCS, turnover margin, turf/dome. Logistic regression, fit on every finished game with a closing
total. Out of sample, picks where it said 56%+ won 55.6% (2018-22, 656) and 53.4% (2023-26, 481)
against the closing total; below 56% it was 51-52% (no edge). Only 56%+ is a bet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BET_AT = 0.56


def features(df: pd.DataFrame) -> pd.DataFrame:
    """df: cfbmodel.pipeline.load() rows with spread_close (home expected margin) and total_line."""
    d = df[df["spread_close"].notna() & df["total_line"].notna()].copy().sort_values("gameday")
    last, hp, ap = {}, [], []
    for r in d.itertuples(index=False):
        hp.append(last.get((r.season, r.home_team), 0.0)); ap.append(last.get((r.season, r.away_team), 0.0))
        if pd.notna(r.result):
            last[(r.season, r.home_team)], last[(r.season, r.away_team)] = r.result, -r.result
    line, open_ = d["spread_close"], d["spread_open"].fillna(d["spread_close"])
    X = pd.DataFrame({
        "line": line, "abs_line": line.abs(), "line_move": line - open_,
        "total_line": d["total_line"], "total_move": d["total_line"] - d["total_open"].fillna(d["total_line"]),
        "key3": (line.abs() == 3).astype(int), "key7": (line.abs() == 7).astype(int),
        "rest_diff": d["rest_diff"].clip(-10, 10), "home_rest": d["home_rest"].clip(3, 15), "away_rest": d["away_rest"].clip(3, 15),
        "home_qb_change": d["home_qb_change"].fillna(0), "away_qb_change": d["away_qb_change"].fillna(0),
        "home_new_qb": d["home_new_qb"].fillna(0), "away_new_qb": d["away_new_qb"].fillna(0),
        "home_prev": pd.Series(hp, index=d.index).clip(-45, 45), "away_prev": pd.Series(ap, index=d.index).clip(-45, 45),
        "neutral": d["neutral"].fillna(0).astype(int), "conf": d["conf_game"].fillna(0).astype(int),
        "fcs_diff": d["fcs_diff"].fillna(0), "week": d["week"], "early": d["early_season"].fillna(0),
        "travel_diff": d["travel_diff"].fillna(0), "tz_diff": d["tz_diff"].fillna(0),
        "turf": d["turf"].fillna(0), "dome": d["dome"].fillna(0), "to_diff": d["to_diff"].fillna(0),
    }, index=d.index)
    out = pd.concat([d[["game_id", "season", "week", "gameday", "home_team", "away_team", "result", "total"]],
                     X.add_prefix("x_")], axis=1)
    m = out["result"] - line
    t = out["total"] - out["x_total_line"]
    out["y_cover"] = np.where(m == 0, np.nan, (m > 0).astype(float))
    out["y_over"] = np.where(t == 0, np.nan, (t > 0).astype(float))
    out.loc[out["result"].isna(), ["y_cover", "y_over"]] = np.nan
    return out


def total_probs(df: pd.DataFrame, game_ids) -> pd.Series:
    """P(over the given total) for game_ids; df must carry their spread_close/total_line (the card's lines)."""
    d = features(df)
    feats = [c for c in d if c.startswith("x_")]
    tr = d[d["y_over"].notna()]
    m = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000)).fit(tr[feats].fillna(0), tr["y_over"])
    te = d[d["game_id"].isin(set(game_ids))]
    return pd.Series(m.predict_proba(te[feats].fillna(0))[:, 1], index=te["game_id"].values)
