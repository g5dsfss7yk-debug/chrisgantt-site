"""Extra inputs tested Nov 23 2026 (v2/test_three.py): special teams split by unit, and each
defense's pass rushers listed Out/Doubtful. Cached under data/raw/."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd

from nflmodel import data, teams

ST_COLS = ["game_id", "posteam", "defteam", "play_type", "epa", "special_teams_play"]
ST_UNITS = ["fg_epa", "punt_epa", "punt_ret_epa", "ko_ret_epa", "ko_cov_epa"]


def _st_season(s: int) -> pd.DataFrame | None:
    path = data.RAW / "pbp_st" / f"{s}.csv"
    live = s >= data.current_season()
    if path.exists() and not live:
        return pd.read_csv(path)
    tmp = data._fetch(f"{data.RELEASE}/pbp/play_by_play_{s}.csv.gz", data.RAW / f"pbp_st_tmp{s}.csv.gz", refresh=True)
    if tmp is None:
        return None
    d = pd.read_csv(tmp, usecols=lambda c: c in ST_COLS, low_memory=False)
    tmp.unlink()
    d = d[d.posteam.notna() & d.defteam.notna() & d.epa.notna()]
    rows = []
    # EPA is from the offense's (posteam's) side. On punts and field goals posteam is the kicking team;
    # on kickoffs it is the receiving team.
    for unit, pt, side, sign in (("fg_epa", ["field_goal", "extra_point"], "posteam", 1),
                                 ("punt_epa", ["punt"], "posteam", 1), ("punt_ret_epa", ["punt"], "defteam", -1),
                                 ("ko_ret_epa", ["kickoff"], "posteam", 1), ("ko_cov_epa", ["kickoff"], "defteam", -1)):
        x = d[d.play_type.isin(pt)].groupby(["game_id", side])["epa"].sum() * sign
        x.index.names = ["game_id", "team"]
        rows.append(x.rename(unit))
    out = pd.concat(rows, axis=1).fillna(0).reset_index()
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def special_teams(seasons) -> pd.DataFrame:
    return pd.concat([f for s in seasons if (f := _st_season(s)) is not None], ignore_index=True)


def _release(kind: str, fname: str, s: int) -> pd.DataFrame | None:
    path = data._fetch(f"{data.RELEASE}/{kind}/{fname}", data.RAW / kind / f"{s}.csv",
                       live=(s >= data.current_season()))
    return None if path is None else pd.read_csv(path, low_memory=False)


def pass_rush_out(seasons, window: int = 8) -> pd.DataFrame:
    """Per (season, week, team): share of the defense's recent sacks + QB hits made by players the
    injury report lists Out or Doubtful for that week. Share is over the team's previous `window`
    games (the report is known before kickoff; the game itself is not used)."""
    st, inj = [], []
    for s in seasons:
        a = _release("stats_player", f"stats_player_week_{s}.csv", s)
        b = _release("injuries", f"injuries_{s}.csv", s)
        if a is not None:
            st.append(a[["player_id", "season", "week", "team", "def_sacks", "def_qb_hits"]])
        if b is not None:
            inj.append(b[["season", "week", "team", "gsis_id", "report_status"]])
    st, inj = pd.concat(st), pd.concat(inj)
    st["team"], inj["team"] = st.team.map(teams.franchise), inj.team.map(teams.franchise)
    st["pr"] = st.def_sacks.fillna(0) + st.def_qb_hits.fillna(0)
    st = st[st.pr > 0]
    out = inj[inj.report_status.isin(["Out", "Doubtful"])]
    games = st[["season", "week", "team"]].drop_duplicates().sort_values(["team", "season", "week"])
    games["k"] = games.groupby("team").cumcount()
    st = st.merge(games, on=["season", "week", "team"])
    res = []
    for (season, week, team), o in out.groupby(["season", "week", "team"]):
        g = games[(games.team == team) & ((games.season < season) | ((games.season == season) & (games.week < week)))]
        if len(g) < 4:
            continue
        ks = g.k.iloc[-window:]
        recent = st[(st.team == team) & st.k.isin(ks)]
        tot = recent.pr.sum()
        share = recent[recent.player_id.isin(o.gsis_id)].pr.sum() / tot if tot else 0.0
        res.append((season, week, team, share))
    return pd.DataFrame(res, columns=["season", "week", "team", "rush_out"])
