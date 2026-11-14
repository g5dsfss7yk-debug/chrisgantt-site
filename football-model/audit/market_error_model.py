"""Audit H: a different model - predict the CLOSING LINE's mistakes from situations only.

The old models predict scores from team strength; the market already prices team strength, so
they mostly echo the line. This one never sees team strength. It learns whether the home team
covers the closing spread (and whether the game goes over the closing total) from situational
inputs: QB changes, rest, line and total movement, weather, division, week, last game's margin,
the size of the line. Walk-forward: each season is predicted by a model fit only on earlier
seasons (from 2009). Graded against the closing line; a -110 bet needs 52.4%.

    python audit/market_error_model.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nflmodel import data, pipeline


def build() -> pd.DataFrame:
    df = pipeline.load()
    d = df[(df["season"] >= 2009) & df["spread_line"].notna() & df["total_line"].notna()].copy()
    raw = data.load_games()[["game_id", "home_rest", "away_rest", "roof", "home_qb_id", "away_qb_id"]]
    d = d.drop(columns=[c for c in ("home_rest", "away_rest", "roof") if c in d]).merge(raw, on="game_id", how="left")
    d = d.sort_values("gameday").reset_index(drop=True)
    last, lastqb = {}, {}
    hp, ap, hq, aq = [], [], [], []
    for r in d.itertuples(index=False):
        hp.append(last.get((r.season, r.home_team), 0.0)); ap.append(last.get((r.season, r.away_team), 0.0))
        hq.append(int(lastqb.get((r.season, r.home_team), r.home_qb_id) != r.home_qb_id))
        aq.append(int(lastqb.get((r.season, r.away_team), r.away_qb_id) != r.away_qb_id))
        lastqb[(r.season, r.home_team)], lastqb[(r.season, r.away_team)] = r.home_qb_id, r.away_qb_id
        if pd.notna(r.result):
            last[(r.season, r.home_team)], last[(r.season, r.away_team)] = r.result, -r.result
    d["home_prev"], d["away_prev"], d["home_qb_change"], d["away_qb_change"] = hp, ap, hq, aq
    line, open_ = d["spread_line"], d["spread_open"].fillna(d["spread_line"])
    X = pd.DataFrame({
        "line": line, "abs_line": line.abs(), "line_move": line - open_,
        "total_line": d["total_line"], "total_move": d["total_line"] - d["total_open"].fillna(d["total_line"]),
        "key3": (line.abs() == 3).astype(int), "key7": (line.abs() == 7).astype(int),
        "home_rest": d["home_rest"].clip(3, 15), "away_rest": d["away_rest"].clip(3, 15),
        "rest_diff": (d["home_rest"] - d["away_rest"]).clip(-10, 10),
        "home_qb_change": d["home_qb_change"], "away_qb_change": d["away_qb_change"],
        "home_prev": d["home_prev"].clip(-35, 35), "away_prev": d["away_prev"].clip(-35, 35),
        "div": d["div_game"].fillna(0), "week": d["week"],
        "prime": ((d["gametime"].astype(str) >= "19:00")
                  | pd.to_datetime(d["gameday"]).dt.day_name().isin(["Monday", "Thursday"])).astype(int),
        "wind": d["wind"].fillna(0), "cold": (45 - d["temp"].fillna(60)).clip(lower=0),
        "dome": d["roof"].isin(["dome", "closed"]).astype(int),
    })
    d = pd.concat([d[["game_id", "season", "week", "gameday", "home_team", "away_team", "result", "total",
                      "spread_line", "total_line"]], X.add_prefix("x_")], axis=1)
    m = d["result"] - d["spread_line"]
    t = d["total"] - d["total_line"]
    d["y_cover"] = np.where(m == 0, np.nan, (m > 0).astype(float))
    d["y_over"] = np.where(t == 0, np.nan, (t > 0).astype(float))
    d.loc[d["result"].isna(), ["y_cover", "y_over"]] = np.nan
    return d


def build_cfb() -> pd.DataFrame:
    """College version: same idea, college situational inputs (travel, neutral site, FCS, conference
    game, QB change/new QB, rest, line and total movement, last margin, turnover margin)."""
    from cfbmodel import pipeline as cp
    d = cp.load()
    d = d[d["spread_close"].notna() & d["total_line"].notna()].copy().sort_values("gameday").reset_index(drop=True)
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
        "home_prev": pd.Series(hp).clip(-45, 45), "away_prev": pd.Series(ap).clip(-45, 45),
        "neutral": d["neutral"].fillna(0).astype(int), "conf": d["conf_game"].fillna(0).astype(int),
        "fcs_diff": d["fcs_diff"].fillna(0), "week": d["week"], "early": d["early_season"].fillna(0),
        "travel_diff": d["travel_diff"].fillna(0), "tz_diff": d["tz_diff"].fillna(0),
        "turf": d["turf"].fillna(0), "dome": d["dome"].fillna(0), "to_diff": d["to_diff"].fillna(0),
    })
    d = pd.concat([d[["game_id", "season", "week", "gameday", "home_team", "away_team", "result", "total"]],
                   X.add_prefix("x_")], axis=1)
    m = d["result"] - line.values
    t = d["total"] - d["x_total_line"]
    d["y_cover"] = np.where(m == 0, np.nan, (m > 0).astype(float))
    d["y_over"] = np.where(t == 0, np.nan, (t > 0).astype(float))
    d.loc[d["result"].isna(), ["y_cover", "y_over"]] = np.nan
    return d


LEARNERS = {
    "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000)),
    "boosted": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.03, max_iter=200,
                                                      min_samples_leaf=80, random_state=0),
}


def walk_forward(d, target, learner, first=2015):
    feats = [c for c in d if c.startswith("x_")]
    out = []
    for s in range(first, int(d["season"].max()) + 1):
        tr = d[(d["season"] < s) & d[target].notna()]
        te = d[d["season"] == s].copy()
        m = LEARNERS[learner]().fit(tr[feats].fillna(0), tr[target])
        te["p"] = m.predict_proba(te[feats].fillna(0))[:, 1]
        out.append(te)
    return pd.concat(out)


if __name__ == "__main__":
    league = sys.argv[1] if len(sys.argv) > 1 else "nfl"
    d = build() if league == "nfl" else build_cfb()
    first = 2015 if league == "nfl" else 2018
    print(f"=== {league.upper()} ===")
    for target, label in (("y_cover", "home covers closing spread"), ("y_over", "over the closing total")):
        for learner in LEARNERS:
            p = walk_forward(d, target, learner, first)
            p = p[p[target].notna()]
            p["pick_won"] = np.where(p["p"] >= 0.5, p[target] == 1, p[target] == 0)
            p["conf"] = (p["p"] - 0.5).abs()
            print(f"\n{label} - {learner} (walk-forward, each season fit on earlier seasons only)")
            for lo in (0.0, 0.02, 0.04, 0.06):
                for per, q in ((f"{first}-22", p[p.season <= 2022]), ("2023-26", p[p.season >= 2023])):
                    x = q[q["conf"] >= lo]
                    print(f"  picks with model {50 + lo * 100:.0f}%+  {per}: {x['pick_won'].mean():.1%} of {len(x)}")
