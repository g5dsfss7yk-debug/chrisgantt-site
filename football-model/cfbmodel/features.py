"""College features, built game by game so each row only uses what was known before kickoff.

Each team carries opponent-adjusted ratings that update after every game and are pulled
toward the league average between seasons. Ratings are keyed by ESPN team id.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

# Per-team stats rated from play-by-play. "def_" ratings are what the defense allowed,
# except havoc and takeaways, which the defense created.
OFF = {"epa": "epa", "sr": "sr", "exp": "explosive", "havoc": "havoc", "sack": "sack"}
PRIOR_GAMES = 3          # preseason rating counts as this many games
CARRY = 0.6              # share of last season's rating kept over the offseason
MIN_ALPHA = 0.12         # floor on how much one game moves a rating
HFA = 2.5                # home-field points used inside the margin rating
FCS_ELO = 1100           # CFBD gives FCS teams no Elo


class Team:
    def __init__(self, league: dict):
        self.r = dict(league)
        self.n = PRIOR_GAMES
        self.season = None
        self.last_day = None
        self.qb_last = None
        self.qb_starts = defaultdict(int)
        self.qb_prev_season = None
        self.games = 0


class League:
    def __init__(self):
        self.mean = {"epa": 0.03, "sr": 0.43, "exp": 0.075, "havoc": 0.128, "sack": 0.031, "pass": 0.49,
                     "plays": 68.0, "rz": 0.58, "st": 0.9, "give": 1.33, "pts": 0.0, "ppg": 28.0}
        self.base = {**{f"off_{k}": v for k, v in self.mean.items()},
                     **{f"def_{k}": v for k, v in self.mean.items()}}
        self.teams: dict[int, Team] = {}
        self.season = None
        self._sum, self._n = defaultdict(float), 0

    def team(self, tid, season) -> Team:
        t = self.teams.get(tid)
        if t is None:
            t = self.teams[tid] = Team(self.base)
        if t.season != season:
            if t.season is not None:
                for k, v in t.r.items():
                    t.r[k] = CARRY * v + (1 - CARRY) * self.base[k]
                t.qb_prev_season = max(t.qb_starts, key=t.qb_starts.get) if t.qb_starts else None
            t.season, t.n, t.games, t.qb_starts = season, PRIOR_GAMES, 0, defaultdict(int)
        return t

    def new_season(self, season):
        if self._n:  # last season's averages become this season's baseline
            for k in self.mean:
                self.mean[k] = self._sum[k] / self._n
            self.base = {**{f"off_{k}": v for k, v in self.mean.items()},
                         **{f"def_{k}": v for k, v in self.mean.items()}}
        self.season, self._sum, self._n = season, defaultdict(float), 0

    def update(self, home: Team, away: Team, hs: pd.Series | None, as_: pd.Series | None,
               margin: float, hpts: float, apts: float, neutral: bool):
        hfa = 0 if neutral else HFA
        pre_h, pre_a = dict(home.r), dict(away.r)
        for t, me, opp, pts_for, pts_against, m in ((home, hs, pre_a, hpts, apts, margin - hfa),
                                                     (away, as_, pre_h, apts, hpts, -margin + hfa)):
            # off_pts is the team's margin rating: margin vs this opponent plus their rating
            obs = {"off_pts": m + opp["off_pts"],
                   "off_ppg": pts_for - (opp["def_ppg"] - self.mean["ppg"]),
                   "def_ppg": pts_against - (opp["off_ppg"] - self.mean["ppg"])}
            if me is not None:
                theirs = as_ if t is home else hs
                for k, col in OFF.items():
                    # offense: adjust for the opposing defense; defense: for the opposing offense
                    obs[f"off_{k}"] = me[col] - (opp[f"def_{k}"] - self.mean[k])
                    if theirs is not None:
                        obs[f"def_{k}"] = theirs[col] - (opp[f"off_{k}"] - self.mean[k])
                obs["off_pass"], obs["off_plays"] = me["pass_rate"], me["plays"]
                if me["rz_trips"] > 0:
                    obs["off_rz"] = me["rz_tds"] / me["rz_trips"]
                obs["off_st"], obs["off_give"] = me["st_epa"], me["giveaways"]
                if theirs is not None:
                    obs["def_plays"] = theirs["plays"]
                    obs["def_give"] = theirs["giveaways"]
                    if theirs["rz_trips"] > 0:
                        obs["def_rz"] = theirs["rz_tds"] / theirs["rz_trips"]
            a = max(MIN_ALPHA, 1 / (t.n + 1))
            for k, v in obs.items():
                if pd.notna(v):
                    t.r[k] += a * (v - t.r[k])
            t.n += 1
            if me is not None:
                for k, col in OFF.items():
                    self._sum[k] += me[col] / 2
                self._sum["pass"] += me["pass_rate"] / 2
                self._sum["plays"] += me["plays"] / 2
                self._sum["give"] += me["giveaways"] / 2
                self._sum["st"] += me["st_epa"] / 2
            self._sum["ppg"] += pts_for / 2
        self._n += 1


def build(games: pd.DataFrame, team_games: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    tg = team_games.set_index(["game_id", "team_id"])
    meta = team_games.drop_duplicates("game_id").set_index("game_id")[["espn_spread", "espn_total"]]
    lines = lines.set_index("game_id")
    L = League()
    rows = []
    for g in games.itertuples(index=False):
        if g.season != L.season:
            L.new_season(g.season)
        h, a = L.team(g.home_id, g.season), L.team(g.away_id, g.season)
        day = g.gameday
        row = {"game_id": g.game_id, "season": g.season, "week": g.week, "gameday": day,
               "kickoff_et": g.kickoff_et, "home_team": g.home_team, "away_team": g.away_team,
               "home_id": g.home_id, "away_id": g.away_id, "result": g.result, "total": g.total,
               "neutral": bool(g.neutral_site), "home_field": 0 if g.neutral_site else 1,
               "conf_game": int(bool(g.conference_game)),
               "postseason": int(g.season_type != "regular")}
        he = g.home_pregame_elo if pd.notna(g.home_pregame_elo) else FCS_ELO
        ae = g.away_pregame_elo if pd.notna(g.away_pregame_elo) else FCS_ELO
        row["elo_diff"] = he - ae
        row["home_fcs"] = int(g.home_division != "fbs")
        row["away_fcs"] = int(g.away_division != "fbs")
        for k in list(OFF) + ["pts", "ppg", "rz", "st", "give", "plays", "pass"]:
            row[f"home_off_{k}"], row[f"away_off_{k}"] = h.r[f"off_{k}"], a.r[f"off_{k}"]
            row[f"home_def_{k}"], row[f"away_def_{k}"] = h.r[f"def_{k}"], a.r[f"def_{k}"]
        for side, t in (("home", h), ("away", a)):
            rest = (day - t.last_day).days if t.last_day is not None and t.games else 14
            row[f"{side}_rest"] = min(rest, 21)
            row[f"{side}_games"] = t.games
            top = max(t.qb_starts, key=t.qb_starts.get) if t.qb_starts else None
            # last game's starter wasn't the team's usual QB: likely injury or benching
            row[f"{side}_qb_change"] = int(top is not None and t.qb_last is not None and t.qb_last != top)
            row[f"{side}_new_qb"] = int(t.qb_prev_season is not None and top is not None and top != t.qb_prev_season)
            row[f"{side}_qb"] = t.qb_last
        for k, v in (meta.loc[g.game_id] if g.game_id in meta.index else {}).items():
            row[k] = v
        if g.game_id in lines.index:
            for k, v in lines.loc[g.game_id].items():
                row[k] = v
        rows.append(row)
        if pd.notna(g.result):
            hs = tg.loc[(g.game_id, g.home_id)] if (g.game_id, g.home_id) in tg.index else None
            as_ = tg.loc[(g.game_id, g.away_id)] if (g.game_id, g.away_id) in tg.index else None
            L.update(h, a, hs, as_, g.result, g.home_points, g.away_points, bool(g.neutral_site))
            for t, s in ((h, hs), (a, as_)):
                t.last_day, t.games = day, t.games + 1
                if s is not None and isinstance(s["qb"], str):
                    t.qb_last = s["qb"]
                    t.qb_starts[s["qb"]] += 1
    df = pd.DataFrame(rows)
    return _derive(df)


def _derive(df: pd.DataFrame) -> pd.DataFrame:
    d = df
    for k in list(OFF) + ["pts", "ppg", "rz", "st", "give"]:
        if k in ("havoc", "sack"):
            # rates against the offense: home defense + away offense's rate allowed, minus the reverse
            d[f"{k}_diff"] = (d[f"home_def_{k}"] + d[f"away_off_{k}"]) - (d[f"away_def_{k}"] + d[f"home_off_{k}"])
        elif k == "give":
            d["to_diff"] = (d["away_off_give"] - d["home_off_give"]) + (d["home_def_give"] - d["away_def_give"])
        elif k == "pts":
            d["pts_diff"] = d["home_off_pts"] - d["away_off_pts"]
        else:
            # home offense against what the away defense allows, minus the reverse
            d[f"{k}_diff"] = (d[f"home_off_{k}"] + d[f"away_def_{k}"]) - (d[f"away_off_{k}"] + d[f"home_def_{k}"])
    d["rest_diff"] = d["home_rest"] - d["away_rest"]
    d["home_off_bye"] = (d["home_rest"] >= 13).astype(int)
    d["away_off_bye"] = (d["away_rest"] >= 13).astype(int)
    d["fcs_diff"] = d["away_fcs"] - d["home_fcs"]
    d["early_season"] = (d[["home_games", "away_games"]].min(axis=1) < 3).astype(int)
    # totals
    d["plays_sum"] = d[["home_off_plays", "away_off_plays", "home_def_plays", "away_def_plays"]].sum(axis=1) / 2
    d["pass_sum"] = d["home_off_pass"] + d["away_off_pass"]
    for k in ("epa", "sr", "exp", "ppg", "rz"):
        d[f"{k}_off_sum"] = d[f"home_off_{k}"] + d[f"away_off_{k}"]
        d[f"{k}_def_sum"] = d[f"home_def_{k}"] + d[f"away_def_{k}"]
    d["havoc_sum"] = d["home_def_havoc"] + d["away_def_havoc"]
    # Lines: opener when the books file has it (and it agrees with the close), else ESPN's.
    if "spread_open" not in d:
        d["spread_open"] = np.nan
    bad = (d["spread_open"] - d["espn_spread"]).abs() > 21
    d.loc[bad, "spread_open"] = np.nan
    d["spread_close"] = d["espn_spread"]
    d["spread_open"] = d["spread_open"].fillna(d["spread_close"])
    d["total_line"] = d["espn_total"]
    return d
