"""V2 NFL model, built from scratch (Nov 15 2026). Shares no code with the old model.

Each team carries exponentially weighted play-by-play ratings (offense and defense EPA/play,
success rate, explosive rate, turnovers, special teams), updated after every game and pulled
toward average at each new season. A ridge regression turns the home-minus-away ratings, rest,
QB change and the line into a predicted margin and total. Walk-forward: every season is
predicted by a model fit only on earlier seasons.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from nflmodel import data, teams

STATS = ["epa", "sr", "explosive", "giveaways", "st_epa", "plays"]
HALF_LIFE = 4          # games (picked on 2015-22 only, see v2/grid.py)
CARRY = 0.65           # share of last season kept at a new season
FIRST_TEST = 2015


def team_games() -> pd.DataFrame:
    g = data.load_games()
    g = g[g["game_type"].isin(["REG", "WC", "DIV", "CON", "SB"])].copy()
    p = data.load_team_pbp(range(2008, data.current_season() + 1))
    p["team"] = p["team"].map(teams.franchise)
    g["home_fr"], g["away_fr"] = g["home_team"].map(teams.franchise), g["away_team"].map(teams.franchise)
    return g, p


def ratings(g: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Pre-game ratings for both teams of every game (only earlier games are used)."""
    p = p.set_index(["game_id", "team"])
    a = 1 - 0.5 ** (1 / HALF_LIFE)
    st, season_of, mean = {}, {}, {}
    rows = []
    g = g.sort_values(["gameday", "gametime", "game_id"])
    for r in g.itertuples(index=False):
        rec = {"game_id": r.game_id}
        for side, t in (("home", r.home_fr), ("away", r.away_fr)):
            if t in st and season_of[t] != r.season:  # new season: pull toward average
                st[t] = {k: CARRY * v + (1 - CARRY) * mean.get(k, v) for k, v in st[t].items()}
                season_of[t] = r.season
            s = st.get(t, {})
            for k, v in s.items():
                rec[f"{side}_{k}"] = v
            rec[f"{side}_n"] = s.get("n", 0)
        rows.append(rec)
        if pd.isna(r.result):
            continue
        for t, o in ((r.home_fr, r.away_fr), (r.away_fr, r.home_fr)):
            if (r.game_id, t) not in p.index or (r.game_id, o) not in p.index:
                continue
            off, dfn = p.loc[(r.game_id, t)], p.loc[(r.game_id, o)]
            obs = {f"o_{k}": off[k] for k in STATS} | {f"d_{k}": dfn[k] for k in STATS}
            pts_for = r.home_score if t == r.home_fr else r.away_score
            pts_ag = r.away_score if t == r.home_fr else r.home_score
            obs |= {"pf": pts_for, "pa": pts_ag}
            s = st.setdefault(t, {})
            season_of.setdefault(t, r.season)
            for k, v in obs.items():
                v = 0.0 if pd.isna(v) else float(v)
                s[k] = v if k not in s else (1 - a) * s[k] + a * v
                mean[k] = v if k not in mean else 0.995 * mean[k] + 0.005 * v
            s["n"] = s.get("n", 0) + 1
    return pd.DataFrame(rows)


def build() -> pd.DataFrame:
    g, p = team_games()
    rt = ratings(g, p)
    d = g.merge(rt, on="game_id")
    n = data.load_nfelo()[["season", "week", "home_fr", "home_line_open", "total_line_open"]]
    d = d.merge(n, on=["season", "week", "home_fr"], how="left")
    d["spread_open"] = -d["home_line_open"]           # + = home favored, like spread_line
    d["total_open"] = d["total_line_open"]
    # QB change vs the team's previous starter (same season)
    d = d.sort_values("gameday").reset_index(drop=True)
    last, hq, aq = {}, [], []
    for r in d.itertuples(index=False):
        hq.append(int(last.get((r.season, r.home_fr), r.home_qb_id) != r.home_qb_id))
        aq.append(int(last.get((r.season, r.away_fr), r.away_qb_id) != r.away_qb_id))
        last[(r.season, r.home_fr)], last[(r.season, r.away_fr)] = r.home_qb_id, r.away_qb_id
    d["home_qb_change"], d["away_qb_change"] = hq, aq
    return d


def X(d: pd.DataFrame, line: pd.Series, kind: str) -> pd.DataFrame:
    f = {}
    for k in STATS:
        if kind == "spread":
            f[f"off_{k}"] = d[f"home_o_{k}"] - d[f"away_o_{k}"]
            f[f"def_{k}"] = d[f"home_d_{k}"] - d[f"away_d_{k}"]
            f[f"m_{k}"] = (d[f"home_o_{k}"] - d[f"away_d_{k}"]) - (d[f"away_o_{k}"] - d[f"home_d_{k}"])
        else:
            f[f"sum_o_{k}"] = d[f"home_o_{k}"] + d[f"away_o_{k}"]
            f[f"sum_d_{k}"] = d[f"home_d_{k}"] + d[f"away_d_{k}"]
    if kind == "spread":
        f["pts"] = (d["home_pf"] - d["home_pa"]) - (d["away_pf"] - d["away_pa"])
        f["rest"] = (d["home_rest"] - d["away_rest"]).clip(-7, 7)
        f["qb"] = d["home_qb_change"] - d["away_qb_change"]
        f["neutral"] = (d["location"] == "Neutral").astype(int)
    else:
        f["pts"] = d["home_pf"] + d["home_pa"] + d["away_pf"] + d["away_pa"]
        f["wind"] = d["wind"].fillna(0).where(~d["roof"].isin(["dome", "closed"]), 0)
        f["dome"] = d["roof"].isin(["dome", "closed"]).astype(int)
        f["qb"] = d["home_qb_change"] + d["away_qb_change"]
    f["line"] = line
    x = pd.DataFrame(f).fillna(0)
    early = (d[["home_n", "away_n"]].fillna(0).min(axis=1) < 3).astype(float)
    # early in a team's history the ratings are thin: let the line carry more
    for c in x:
        if c != "line":
            x[c] = x[c] * (1 - 0.5 * early)
    return x


def fit(train: pd.DataFrame, kind: str, line_col: str):
    y = train["result"] if kind == "spread" else train["total"]
    m = Ridge(alpha=30.0).fit(X(train, train[line_col], kind), y)
    return m


def walk_forward(d: pd.DataFrame, kind: str, line_col: str) -> pd.DataFrame:
    out = []
    done = d[d["result"].notna() & d[line_col].notna() & (d["season"] >= 2009)]
    for s in range(FIRST_TEST, int(d["season"].max()) + 1):
        tr = done[done["season"] < s]
        te = d[(d["season"] == s) & d[line_col].notna()].copy()
        m = fit(tr, kind, line_col)
        te["pred"] = m.predict(X(te, te[line_col], kind))
        out.append(te)
    return pd.concat(out)
