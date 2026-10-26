"""Anytime-touchdown props: P(a player scores a rushing or receiving TD in a game).

Built from nflverse weekly player stats plus red-zone usage from play-by-play. Each row
uses only games before it: the player's share of his team's red-zone and goal-line
touches, carries and targets, recent TD rate, his team's implied points from the betting
line, and how often the opponent gives up touchdowns. No free archive of historical prop
odds exists, so the model is checked for calibration (do 30% players score 30% of the
time?) and against a simple season-TD-rate baseline, not for profit against books.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nflmodel import data, teams

FIRST_SEASON = 2013
POSITIONS = ("RB", "WR", "TE", "QB")
ALPHA = 0.3          # weight of the latest game in the running averages
CARRY = 0.5          # share of last season's averages kept at the start of a season

FEATURES = [
    "rz_share", "gl_share", "carry_share", "target_share", "td_rate", "touches",
    "rz_touches", "gl_touches", "implied_pts", "opp_td_allowed", "home", "games",
    "is_rb", "is_wr", "is_te", "is_qb",
]


def _player_pbp(season: int, refresh: bool = False) -> pd.DataFrame:
    """Per player-game red-zone (inside 20) and goal-line (inside 5) carries and targets."""
    path = data.RAW / "pbp_player" / f"{season}.csv"
    if path.exists() and not refresh and season != data.current_season():
        return pd.read_csv(path)
    tmp = data._fetch(f"{data.RELEASE}/pbp/play_by_play_{season}.csv.gz", data.RAW / "pbp_tmp.csv.gz", refresh=True)
    cols = ["game_id", "posteam", "yardline_100", "play_type", "rusher_player_id", "receiver_player_id",
            "two_point_attempt"]
    p = pd.read_csv(tmp, usecols=cols, low_memory=False)
    p = p[p["play_type"].isin(["run", "pass"]) & (p["two_point_attempt"] != 1)]
    out = []
    for col in ("rusher_player_id", "receiver_player_id"):
        x = p.dropna(subset=[col]).rename(columns={col: "player_id"})
        out.append(x.assign(rz=x["yardline_100"] <= 20, gl=x["yardline_100"] <= 5))
    x = pd.concat(out)
    team = p.assign(rz=p["yardline_100"] <= 20, gl=p["yardline_100"] <= 5).groupby(["game_id", "posteam"])[
        ["rz", "gl"]].sum().add_prefix("team_").reset_index()
    pl = x.groupby(["game_id", "posteam", "player_id"])[["rz", "gl"]].sum().reset_index()
    pl = pl.merge(team, on=["game_id", "posteam"])
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.to_csv(path, index=False)
    tmp.unlink()
    return pl


def load_player_games(refresh: bool = False) -> pd.DataFrame:
    out = []
    for s in range(FIRST_SEASON, data.current_season() + 1):
        path = data._fetch(f"{data.RELEASE}/stats_player/stats_player_week_{s}.csv",
                           data.RAW / "stats_player" / f"{s}.csv", refresh, live=s == data.current_season())
        w = pd.read_csv(path, low_memory=False)
        w = w[w["position"].isin(POSITIONS) & (w["season_type"] == "REG")]
        w = w[["player_id", "player_display_name", "position", "season", "week", "game_id", "team",
               "opponent_team", "carries", "targets", "rushing_tds", "receiving_tds"]]
        rz = _player_pbp(s, refresh).drop(columns="posteam")
        out.append(w.merge(rz, on=["game_id", "player_id"], how="left"))
    d = pd.concat(out, ignore_index=True)
    d[["rz", "gl", "team_rz", "team_gl"]] = d[["rz", "gl", "team_rz", "team_gl"]].fillna(0)
    d["td"] = ((d["rushing_tds"] + d["receiving_tds"]) > 0).astype(int)
    d["team"] = d["team"].map(teams.franchise)
    d["opponent_team"] = d["opponent_team"].map(teams.franchise)
    return d


def build(pg: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per player-game with features from earlier games only."""
    team_tot = pg.groupby(["game_id", "team"])[["carries", "targets"]].sum().add_prefix("team_").reset_index()
    pg = pg.merge(team_tot, on=["game_id", "team"])
    stats = {
        "rz_share": pg["rz"] / pg["team_rz"].replace(0, np.nan),
        "gl_share": pg["gl"] / pg["team_gl"].replace(0, np.nan),
        "carry_share": pg["carries"] / pg["team_carries"].replace(0, np.nan),
        "target_share": pg["targets"] / pg["team_targets"].replace(0, np.nan),
        "td_rate": pg["td"].astype(float), "touches": (pg["carries"] + pg["targets"]).astype(float),
        "rz_touches": pg["rz"].astype(float), "gl_touches": pg["gl"].astype(float),
    }
    pg = pg.assign(**{f"g_{k}": v for k, v in stats.items()})
    # contiguous per player, in time order, so the feature rows line up with pg
    pg = pg.sort_values(["player_id", "season", "week"], kind="stable").reset_index(drop=True)
    feats = []
    for _, grp in pg.groupby("player_id", sort=False):
        state, n, last_season = {}, 0, None
        for r in grp.itertuples(index=False):
            if last_season is not None and r.season != last_season:
                state = {k: CARRY * v for k, v in state.items()}
                n = 0
            feats.append({"games": n, **{k: state.get(k, np.nan) for k in stats}})
            for k in stats:
                v = getattr(r, f"g_{k}")
                if pd.notna(v):
                    state[k] = v if k not in state else state[k] + ALPHA * (v - state[k])
            n, last_season = n + 1, r.season
    pg = pd.concat([pg, pd.DataFrame(feats)], axis=1)

    # Opponent: running rate of skill-player TDs allowed per game.
    allowed = pg.groupby(["season", "week", "opponent_team"])["td"].sum().reset_index()
    allowed = allowed.sort_values(["season", "week"])
    allowed["opp_td_allowed"] = allowed.groupby("opponent_team")["td"].transform(
        lambda s: s.shift(1).ewm(alpha=0.15).mean())
    pg = pg.merge(allowed[["season", "week", "opponent_team", "opp_td_allowed"]],
                  on=["season", "week", "opponent_team"], how="left")

    # Team implied points from the closing spread and total (props are bet on game day).
    g = games[["game_id", "home_team", "away_team", "spread_line", "total_line"]].copy()
    g["home_team"], g["away_team"] = g["home_team"].map(teams.franchise), g["away_team"].map(teams.franchise)
    pg = pg.merge(g, on="game_id", how="left")
    pg["home"] = (pg["team"] == pg["home_team"]).astype(int)
    sign = np.where(pg["home"] == 1, 1, -1)
    pg["implied_pts"] = pg["total_line"] / 2 + sign * pg["spread_line"] / 2
    for p in POSITIONS:
        pg[f"is_{p.lower()}"] = (pg["position"] == p).astype(int)
    return pg


LEARNERS = {
    "logit": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=500)),
    "boost": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                                     min_samples_leaf=200, random_state=0),
}


def _X(d):
    return d[FEATURES].fillna(0)


def fit(d: pd.DataFrame):
    d = d[(d["games"] > 0) & d["implied_pts"].notna() & d["td"].notna()]
    return {n: LEARNERS[n]().fit(_X(d), d["td"]) for n in LEARNERS}


def predict(models, d: pd.DataFrame) -> pd.Series:
    return pd.DataFrame({n: m.predict_proba(_X(d))[:, 1] for n, m in models.items()}, index=d.index).mean(axis=1)


def upcoming(pg: pd.DataFrame, games: pd.DataFrame, season: int, week: int,
             injuries: pd.DataFrame | None = None, depth: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rows for this week's games.

    Candidates are the RB/WR/TE/QB on today's depth chart (so a starter returning from
    injury, with no recent games, is included) plus anyone with a touch in the team's last
    two games who is still on the chart. Out/Doubtful players are removed.
    """
    wk = games[(games["season"] == season) & (games["week"] == week)]
    out_ids = set()
    if injuries is not None:
        inj = injuries[(injuries["season"] == season) & (injuries["week"] == week)]
        out_ids = set(inj.loc[inj["report_status"].isin(["Out", "Doubtful"]), "gsis_id"])
    pos = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE"}
    out = []
    for g in wk.itertuples(index=False):
        for team, opp in ((g.home_team, g.away_team), (g.away_team, g.home_team)):
            team, opp = teams.franchise(team), teams.franchise(opp)
            past = pg[(pg["team"] == team) & (pg["season"] == season) & (pg["week"] < week)]
            recent = past[past["week"] >= past["week"].nlargest(2).min()] if len(past) else past
            recent = recent[(recent["carries"] + recent["targets"]) > 0]
            cand = {pid: (r.player_display_name, r.position) for pid, r in recent.groupby("player_id").last().iterrows()}
            if depth is not None:
                from nflmodel.lineups import skill_players
                chart = skill_players(depth[depth["team"] == team])
                on_chart = set(chart["gsis_id"])
                cand = {k: v for k, v in cand.items() if k in on_chart}
                for r in chart.itertuples(index=False):
                    cand.setdefault(r.gsis_id, (r.player_name, pos[r.pos_abb]))
            for pid, (name, position) in cand.items():
                if pid in out_ids:
                    continue
                out.append({"player_id": pid, "player_display_name": name, "position": position,
                            "season": season, "week": week, "game_id": g.game_id, "team": team, "opponent_team": opp})
    return pd.DataFrame(out)


def walk_forward(d: pd.DataFrame, seasons) -> pd.DataFrame:
    out = []
    for s in seasons:
        test = d[(d["season"] == s) & (d["games"] > 0) & d["implied_pts"].notna()]
        out.append(test.assign(p=predict(fit(d[d["season"] < s]), test)))
    return pd.concat(out)
