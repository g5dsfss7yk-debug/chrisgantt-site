"""In-game (live) ladder chances: will a player reach X yards, given what he has now?

Training data: nflverse play-by-play, cut at 7 points in each game (every 7.5 minutes of game
clock). At each cut, a player's yards, carries and targets so far, his team's score margin and
the time left are known; the target is the yards he gains in the rest of the game. Pregame inputs
(his running averages, role, team implied points, spread) come from props.build, which only uses
earlier games, so nothing from the future leaks in.

Model: gradient boosting for rest-of-game yards, plus the empirical distribution of actual
rest-of-game yards for rows with similar predictions (binned), so a ladder chance is
P(rest > rung - 0.5 - yards so far). Backtest: train through 2022, test 2023-26 (audit/live_audit.py).
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from nflmodel import data, teams

CUTS = (3150, 2700, 2250, 1800, 1350, 900, 450)   # game seconds remaining
FIRST = 2018
MARKETS = {"rushing_yards": ("RB", "QB"), "receiving_yards": ("WR", "TE", "RB"), "passing_yards": ("QB",)}
BINS = 30
SPLITS = data.RAW / "live_splits"
PBP_COLS = ["game_id", "season", "week", "home_team", "away_team", "posteam", "game_seconds_remaining",
            "play_type", "two_point_attempt", "rusher_player_id", "receiver_player_id", "passer_player_id",
            "rushing_yards", "receiving_yards", "passing_yards", "pass_attempt", "rush_attempt",
            "total_home_score", "total_away_score"]


def splits(season: int, refresh: bool = False) -> pd.DataFrame:
    """One row per player, game and cut: stats so far, score margin, final stats."""
    path = SPLITS / f"{season}.csv"
    if path.exists() and not refresh and season != data.current_season():
        return pd.read_csv(path)
    tmp = data._fetch(f"{data.RELEASE}/pbp/play_by_play_{season}.csv.gz", data.RAW / f"pbp_live_tmp_{season}.csv.gz",
                      refresh=True)
    p = pd.read_csv(tmp, usecols=PBP_COLS, low_memory=False)
    tmp.unlink()
    p = p[p["game_seconds_remaining"].notna()]
    plays = p[p["play_type"].isin(["run", "pass"]) & (p["two_point_attempt"] != 1)]
    ev = []
    for col, yards, kind in (("rusher_player_id", "rushing_yards", "rush"),
                             ("receiver_player_id", "receiving_yards", "rec"),
                             ("passer_player_id", "passing_yards", "pass")):
        x = plays.dropna(subset=[col])
        ev.append(pd.DataFrame({"game_id": x["game_id"], "team": x["posteam"], "player_id": x[col],
                                "t": x["game_seconds_remaining"], "kind": kind,
                                "yds": x[yards].fillna(0).astype(float), "n": 1.0}))
    ev = pd.concat(ev, ignore_index=True)
    # score margin at each cut, from the last play at or before it
    sc = p.sort_values(["game_id", "game_seconds_remaining"], ascending=[True, False])
    out = []
    final = ev.groupby(["game_id", "team", "player_id", "kind"])["yds"].sum().unstack("kind", fill_value=0)
    for cut in CUTS:
        before = ev[ev["t"] >= cut]
        cur = before.groupby(["game_id", "team", "player_id", "kind"]).agg(yds=("yds", "sum"), n=("n", "sum"))
        cur = cur.unstack("kind", fill_value=0)
        cur.columns = [f"cur_{a}_{b}" for a, b in cur.columns]
        s = sc[sc["game_seconds_remaining"] >= cut].groupby("game_id").last()[
            ["home_team", "away_team", "total_home_score", "total_away_score"]]
        rows = final.add_prefix("final_").join(cur, how="left").fillna(0).reset_index()
        rows = rows.merge(s, left_on="game_id", right_index=True, how="left")
        home = rows["team"] == rows["home_team"]
        rows["margin"] = np.where(home, rows["total_home_score"] - rows["total_away_score"],
                                  rows["total_away_score"] - rows["total_home_score"])
        rows["secs_left"] = cut
        out.append(rows.drop(columns=["home_team", "away_team", "total_home_score", "total_away_score"]))
    df = pd.concat(out, ignore_index=True)
    df["team"] = df["team"].map(teams.franchise)
    for k in ("rush", "rec", "pass"):
        for c in (f"final_{k}", f"cur_yds_{k}", f"cur_n_{k}"):
            if c not in df:
                df[c] = 0.0
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


KIND = {"rushing_yards": "rush", "receiving_yards": "rec", "passing_yards": "pass"}
PRE = ["avg_rushing_yards", "avg_receiving_yards", "avg_passing_yards", "avg_carries", "avg_targets",
       "avg_attempts", "carry_share", "target_share", "snap_pct", "implied_pts", "spread_for", "games"]
LIVE = ["cur_yds", "cur_n", "cur_n_other", "margin", "secs_left", "frac_left"]


def rows_for(market: str, sp: pd.DataFrame, pre: pd.DataFrame) -> pd.DataFrame:
    """Training/backtest rows: splits joined to pregame features (props.build output, prepared)."""
    k = KIND[market]
    other = {"rush": "rec", "rec": "rush", "pass": "rush"}[k]
    x = sp.merge(pre[["game_id", "player_id", "position", "season", "week"] + PRE], on=["game_id", "player_id"])
    x = x[x["position"].isin(MARKETS[market])]
    x = x.assign(cur_yds=x[f"cur_yds_{k}"], cur_n=x[f"cur_n_{k}"], cur_n_other=x[f"cur_n_{other}"],
                 final=x[f"final_{k}"], frac_left=x["secs_left"] / 3600)
    x["rest"] = x["final"] - x["cur_yds"]
    return x


def features(market: str) -> list[str]:
    return PRE + LIVE + ["is_qb", "is_rb", "is_wr", "is_te"]


def _pos(x: pd.DataFrame) -> pd.DataFrame:
    return x.assign(**{f"is_{p.lower()}": (x["position"] == p).astype(int) for p in ("QB", "RB", "WR", "TE")})


class LiveModel:
    def __init__(self, market: str):
        self.market = market

    def fit(self, rows: pd.DataFrame):
        rows = _pos(rows)
        f = features(self.market)
        self.m = HistGradientBoostingRegressor(max_depth=5, learning_rate=0.05, max_iter=400,
                                               min_samples_leaf=200, random_state=0)
        # the distribution comes from out-of-fold predictions so it is not too tight
        folds = rows["season"].values
        pred = np.zeros(len(rows))
        for s in np.unique(folds):
            m = HistGradientBoostingRegressor(max_depth=5, learning_rate=0.05, max_iter=400,
                                              min_samples_leaf=200, random_state=0)
            tr = folds != s
            m.fit(rows.loc[tr, f].fillna(0), rows.loc[tr, "rest"])
            pred[~tr] = m.predict(rows.loc[~tr, f].fillna(0))
        self.m.fit(rows[f].fillna(0), rows["rest"])
        self.edges = np.unique(np.quantile(pred, np.linspace(0, 1, BINS + 1)))
        idx = np.clip(np.searchsorted(self.edges, pred, side="right") - 1, 0, len(self.edges) - 2)
        self.vals = [np.sort(rows["rest"].values[idx == i]) for i in range(len(self.edges) - 1)]
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return self.m.predict(_pos(x)[features(self.market)].fillna(0))

    def p_reach(self, pred: float, cur: float, rung: float) -> float:
        """Chance of finishing at rung+ ('X+' ladder), given yards so far and predicted rest."""
        need = rung - 0.5 - cur
        if need < 0:
            return 1.0
        i = int(np.clip(np.searchsorted(self.edges, pred, side="right") - 1, 0, len(self.vals) - 1))
        v = self.vals[i]
        return float((v > need).mean()) if len(v) else np.nan


# Out of sample (2023-26) the 4th-quarter chances between 30% and 97% ran 3-4 points high
# (said 39/59/80%, hit 36/55/77%); before the 4th they were within 1 point.
Q4_SECS, Q4_ADJ = 1350, 0.035


def adjust(p: float, secs_left: float) -> float:
    return p - Q4_ADJ if secs_left < Q4_SECS and 0.30 <= p < 0.97 else p


# --- live game state from ESPN ---------------------------------------------------------------

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={}"


def game_state(espn_id) -> dict:
    """Score, clock and each player's yards/carries/targets so far from ESPN's live box score."""
    with urllib.request.urlopen(ESPN.format(int(float(espn_id))), timeout=20) as r:
        s = json.load(r)
    comp = s["header"]["competitions"][0]
    st = comp["status"]
    period = int(st.get("period", 0) or 0)
    clock = float(st.get("clock", 0) or 0)
    name = st["type"]["name"]
    if name == "STATUS_HALFTIME":
        secs = 1800.0
    elif period == 0 or st["type"]["state"] == "pre":
        secs = 3600.0
    else:
        secs = max(0.0, (4 - min(period, 4)) * 900 + clock)
    score = {c["homeAway"]: float(c.get("score") or 0) for c in comp["competitors"]}
    side = {c["team"]["abbreviation"]: c["homeAway"] for c in comp["competitors"]}
    players = []
    for t in s.get("boxscore", {}).get("players", []):
        ab = t["team"]["abbreviation"]
        for cat in t["statistics"]:
            if cat["name"] not in ("rushing", "receiving", "passing"):
                continue
            lab = cat["labels"]
            for a in cat["athletes"]:
                v = dict(zip(lab, a["stats"]))
                row = {"side": side.get(ab), "name": a["athlete"]["displayName"], "cat": cat["name"]}
                if cat["name"] == "rushing":
                    row.update(yds=float(v.get("YDS", 0)), n=float(v.get("CAR", 0)))
                elif cat["name"] == "receiving":
                    row.update(yds=float(v.get("YDS", 0)), n=float(v.get("TGTS", v.get("REC", 0))))
                else:
                    row.update(yds=float(v.get("YDS", 0)), n=float(str(v.get("C/ATT", "0/0")).split("/")[-1]))
                players.append(row)
    return {"secs_left": secs, "status": st["type"]["detail"], "score": score, "players": pd.DataFrame(players),
            "final": st["type"].get("completed", False)}
