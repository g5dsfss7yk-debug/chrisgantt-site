"""V2 player props, built from scratch (Nov 15 2026). No code from nflmodel/props.py.

For each stat a gradient-boosting model predicts the player's number from pre-game inputs only
(his exponentially weighted recent games, role, team implied points and spread). The chance of
reaching a ladder rung comes from the actual outcomes of past player-games with similar
predictions (out-of-fold by season), so it is the rate at which such players really got there.
Test: fit on 2015-2022, check 2023-26 (v2/test_props.py).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import re
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from nflmodel import data, teams

RAW = ["carries", "targets", "receptions", "rushing_yards", "receiving_yards", "attempts", "completions",
       "passing_yards", "passing_tds", "rushing_tds", "receiving_tds", "target_share", "air_yards_share", "snap_pct"]
STATS = {  # market -> (positions, how to compute)
    "rushing_yards": (("RB", "QB", "WR"), lambda d: d["rushing_yards"]),
    "receiving_yards": (("WR", "TE", "RB"), lambda d: d["receiving_yards"]),
    "passing_yards": (("QB",), lambda d: d["passing_yards"]),
    "receptions": (("WR", "TE", "RB"), lambda d: d["receptions"]),
    "rush_rec_yards": (("RB", "WR", "TE"), lambda d: d["rushing_yards"] + d["receiving_yards"]),
    "passing_tds": (("QB",), lambda d: d["passing_tds"]),
    "anytime_td": (("RB", "WR", "TE", "QB"), lambda d: d["rushing_tds"] + d["receiving_tds"]),
}
HL = 4
COUNTS = {"receptions", "passing_tds", "anytime_td"}
BINS = 25


def load() -> pd.DataFrame:
    s = pd.concat([pd.read_csv(data.RAW / "stats_player" / f"{y}.csv", low_memory=False)
                   for y in range(2013, data.current_season() + 1)], ignore_index=True)
    s = s[s["position"].isin(["QB", "RB", "WR", "TE"]) & s["season_type"].isin(["REG", "POST"])]
    s["team"] = s["team"].map(teams.franchise)
    g = data.load_games()
    g["home_fr"], g["away_fr"] = g["home_team"].map(teams.franchise), g["away_team"].map(teams.franchise)
    side = pd.concat([
        g.assign(team=g.home_fr, spread_for=g.spread_line, pts=g.total_line / 2 + g.spread_line / 2, home=1),
        g.assign(team=g.away_fr, spread_for=-g.spread_line, pts=g.total_line / 2 - g.spread_line / 2, home=0),
    ])[["game_id", "team", "spread_for", "pts", "home", "gameday"]]
    s = _with_snaps(s)
    s = s.merge(side, on=["game_id", "team"], how="left", suffixes=("", "_g"))
    for c in ("spread_for", "pts", "home", "gameday"):
        s[c] = s[c].fillna(s.pop(f"{c}_g")) if f"{c}_g" in s else s[c]
    for c in RAW + ["snap_pct"]:
        s[c] = s[c].fillna(0)
    return s.sort_values(["player_id", "gameday"]).reset_index(drop=True)


def _key(n):
    import unicodedata
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'\-]", "", n)
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", n).strip()


def _with_snaps(s):
    """Every game a player was on the field on offense counts, even with no stats (the stats
    file has no row for a player who played but recorded nothing - leaving those out makes
    every chance too high)."""
    sn = pd.concat([pd.read_csv(data.RAW / "snap_counts" / f"{y}.csv") for y in range(2013, data.current_season() + 1)
                    if (data.RAW / "snap_counts" / f"{y}.csv").exists()], ignore_index=True)
    sn = sn[(sn["offense_snaps"] >= 1) & sn["position"].isin(["QB", "RB", "WR", "TE", "FB"])]
    sn["team"] = sn["team"].map(teams.franchise)
    sn["k"] = sn["player"].map(_key)
    s["k"] = s["player_display_name"].map(_key)
    ids = s.drop_duplicates(["k", "team", "season"])[["k", "team", "season", "player_id", "player_display_name", "position"]]
    sn = sn.merge(ids, on=["k", "team", "season"], how="left", suffixes=("_sn", ""))
    sn["player_id"] = sn["player_id"].fillna("pfr:" + sn["pfr_player_id"].astype(str))
    sn["player_display_name"] = sn["player_display_name"].fillna(sn["player"])
    sn["position"] = sn["position"].fillna(sn["position_sn"]).replace({"FB": "RB"})
    sn = sn.rename(columns={"offense_pct": "snap_pct"})[["game_id", "team", "season", "week", "player_id",
                                                         "player_display_name", "position", "snap_pct"]]
    s = s.merge(sn[["game_id", "player_id", "snap_pct"]], on=["game_id", "player_id"], how="left")
    extra = sn.merge(s[["game_id", "player_id"]], on=["game_id", "player_id"], how="left", indicator=True)
    extra = extra[extra["_merge"] == "left_only"].drop(columns="_merge").assign(season_type="REG")
    return pd.concat([s, extra], ignore_index=True)


def history(s: pd.DataFrame) -> pd.DataFrame:
    """Pre-game features: EW means of earlier games only (shifted)."""
    g = s.groupby("player_id")
    for c in RAW:
        s[f"ew_{c}"] = g[c].transform(lambda x: x.shift().ewm(halflife=HL, min_periods=1).mean())
        s[f"last_{c}"] = g[c].shift()
    s["n_games"] = g.cumcount()
    s["tds"] = s["rushing_tds"] + s["receiving_tds"]
    s["ew_tds"] = g["tds"].transform(lambda x: x.shift().ewm(halflife=8, min_periods=1).mean())
    return s


def next_game(s: pd.DataFrame) -> pd.DataFrame:
    """Features for each player's NEXT game (EW means including his latest game)."""
    s = s.copy()
    s["tds"] = s["rushing_tds"] + s["receiving_tds"]
    g = s.groupby("player_id")
    out = g.tail(1)[["player_id", "player_display_name", "position", "team", "gameday", "season"]].set_index("player_id")
    for c in RAW:
        out[f"ew_{c}"] = g[c].apply(lambda x: x.ewm(halflife=HL).mean().iloc[-1])
        out[f"last_{c}"] = g[c].last()
    out["ew_tds"] = g["tds"].apply(lambda x: x.ewm(halflife=8).mean().iloc[-1])
    out["n_games"] = g.size()
    return out.reset_index()


def feats() -> list[str]:
    return [f"ew_{c}" for c in RAW] + [f"last_{c}" for c in RAW] + ["ew_tds", "n_games", "pts", "spread_for", "home",
                                                                     "is_qb", "is_rb", "is_wr", "is_te"]


def _pos(x):
    return x.assign(**{f"is_{p.lower()}": (x["position"] == p).astype(int) for p in ("QB", "RB", "WR", "TE")})


class StatModel:
    def __init__(self, market):
        self.market = market
        self.pos, self.f = STATS[market]

    def rows(self, s):
        x = s[s["position"].isin(self.pos) & (s["n_games"] >= 2)].copy()
        x["y"] = self.f(x)
        return _pos(x)

    def _m(self):
        return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=100, random_state=0)

    def fit(self, x):
        F = feats()
        pred = np.zeros(len(x))
        for sea in x["season"].unique():
            tr = x["season"] != sea
            pred[~tr] = self._m().fit(x.loc[tr, F], x.loc[tr, "y"]).predict(x.loc[~tr, F])
        self.m = self._m().fit(x[F], x["y"])
        if self.market == "anytime_td":
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.c = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300,
                                                    min_samples_leaf=100, random_state=0).fit(x[F], x["y"] >= 1)
        self.edges = np.unique(np.quantile(pred, np.linspace(0, 1, BINS + 1)))
        idx = np.clip(np.searchsorted(self.edges, pred, side="right") - 1, 0, len(self.edges) - 2)
        res = x["y"].values if self.market in COUNTS else x["y"].values - pred
        self.vals = [np.sort(res[idx == i]) for i in range(len(self.edges) - 1)]
        return self

    def predict(self, x):
        if self.market == "anytime_td":   # a direct chance from a classifier (no cap at the top)
            return self.c.predict_proba(_pos(x)[feats()])[:, 1]
        return self.m.predict(_pos(x)[feats()])

    def p_reach(self, pred, rung):
        i = int(np.clip(np.searchsorted(self.edges, pred, side="right") - 1, 0, len(self.vals) - 1))
        v = self.vals[i]   # past misses (actual - predicted) of players with similar predictions
        if self.market == "anytime_td":
            return float(pred)
        if self.market in COUNTS:   # whole numbers: actual outcomes of similar players
            return float((v >= rung).mean())
        return float((pred + v >= rung - 1e-9).mean())
