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


def rush_out_all() -> pd.DataFrame:
    """pass_rush_out for 2009 to now. Past seasons are cached in data/raw/rush_out.csv; the current
    season is recomputed each run (injury reports change during the week)."""
    cur = data.current_season()
    path = data.RAW / "rush_out.csv"
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["season"])
    if not set(range(2009, cur)) <= set(old.season.unique()):
        old = pass_rush_out(range(2009, cur))
        old.to_csv(path, index=False)
    new = pass_rush_out([cur - 1, cur])
    return pd.concat([old[old.season < cur], new[new.season == cur]], ignore_index=True)


def qb_values(half_life: float = 20, k: float = 200, first_test: int = 2015) -> pd.DataFrame:
    """Each QB's value BEFORE each game: weighted EPA per play (dropbacks + carries) over his career,
    any team, recent games weighted more (half-life in games), shrunk toward what new QBs produced
    (`k` plays of prior). Prior measured on seasons before `first_test` only."""
    st = []
    for s in range(2009, data.current_season() + 1):
        a = _release("stats_player", f"stats_player_week_{s}.csv", s)
        if a is not None:
            st.append(a[["player_id", "season", "week", "position", "attempts", "sacks_suffered", "carries",
                         "passing_epa", "rushing_epa"]])
    st = pd.concat(st)
    st = st[(st.position == "QB") & (st.attempts.fillna(0) >= 1)].fillna(0).sort_values(["player_id", "season", "week"])
    st["plays"] = st.attempts + st.sacks_suffered + st.carries
    st["epa"] = st.passing_epa + st.rushing_epa
    # prior: QBs' EPA/play while they had under k career plays (seasons before first_test)
    st["career"] = st.groupby("player_id").plays.cumsum() - st.plays
    early = st[(st.career < k) & (st.season < first_test)]
    prior = early.epa.sum() / early.plays.sum()
    dec = 0.5 ** (1 / half_life)
    out = []
    for pid, x in st.groupby("player_id", sort=False):
        e = p = 0.0
        for r in x.itertuples(index=False):
            e, p = dec * e + r.epa, dec * p + r.plays
            out.append((pid, r.season, r.week, (e + prior * k) / (p + k)))   # value AFTER this game
    v = pd.DataFrame(out, columns=["player_id", "season", "week", "qb_val"])
    v.attrs["prior"] = prior
    return v


def qb_value_at(v: pd.DataFrame, ids: pd.Series, seasons: pd.Series, weeks: pd.Series) -> pd.Series:
    """Value of each listed starter going into that game: his latest value from a game before it."""
    prior = v.attrs.get("prior", np.nan)
    v = v.copy()
    v["key"] = (v.season * 100 + v.week).astype(float)
    q = pd.DataFrame({"player_id": ids.values, "key": (seasons * 100 + weeks).values - 0.5, "i": range(len(ids))})
    q = q.sort_values("key")
    m = pd.merge_asof(q, v.sort_values("key")[["player_id", "key", "qb_val"]], on="key", by="player_id")
    # rows hold the value AFTER each game, so the latest row strictly before this game is his pre-game value
    m = m.sort_values("i")
    return pd.Series(m.qb_val.fillna(prior).values, index=ids.index)


def referee_totals(g: pd.DataFrame, k: float = 30) -> pd.Series:
    """Per game: the crew chief's average (total - closing total) in his EARLIER games, shrunk by k games."""
    g = g.sort_values(["gameday", "gametime"])
    s, n, out = {}, {}, {}
    for r in g.itertuples():
        ref = r.referee
        out[r.Index] = (s.get(ref, 0.0) / (n.get(ref, 0) + k)) if isinstance(ref, str) else 0.0
        if isinstance(ref, str) and pd.notna(r.total) and pd.notna(r.total_line):
            s[ref] = s.get(ref, 0.0) + (r.total - r.total_line)
            n[ref] = n.get(ref, 0) + 1
    return pd.Series(out)


SKILL = ("RB", "WR", "TE")


def skill_out(seasons, window: int = 8) -> pd.DataFrame:
    """Per (season, week, team): for RB, WR and TE, the share of the team's scrimmage yards (rushing +
    receiving) over its previous `window` games made by players the injury report lists Out or
    Doubtful that week. The backups take that work, so a high share means backups are playing."""
    st, inj = [], []
    for s in seasons:
        a = _release("stats_player", f"stats_player_week_{s}.csv", s)
        b = _release("injuries", f"injuries_{s}.csv", s)
        if a is not None:
            st.append(a[["player_id", "season", "week", "team", "position_group", "rushing_yards", "receiving_yards"]])
        if b is not None:
            inj.append(b[["season", "week", "team", "gsis_id", "report_status"]])
    st, inj = pd.concat(st), pd.concat(inj)
    st["team"], inj["team"] = st.team.map(teams.franchise), inj.team.map(teams.franchise)
    st = st[st.position_group.isin(SKILL)].copy()
    st["yds"] = st.rushing_yards.fillna(0).clip(lower=0) + st.receiving_yards.fillna(0).clip(lower=0)
    games = st[["season", "week", "team"]].drop_duplicates().sort_values(["team", "season", "week"])
    games["k"] = games.groupby("team").cumcount()
    st = st.merge(games, on=["season", "week", "team"])
    out = inj[inj.report_status.isin(["Out", "Doubtful"])]
    res = []
    for (season, week, team), o in out.groupby(["season", "week", "team"]):
        g = games[(games.team == team) & ((games.season < season) | ((games.season == season) & (games.week < week)))]
        if len(g) < 4:
            continue
        recent = st[(st.team == team) & st.k.isin(g.k.iloc[-window:])]
        tot = recent.yds.sum()
        row = {"season": season, "week": week, "team": team}
        for pg in SKILL:
            r = recent[recent.position_group == pg]
            row[f"{pg.lower()}_out"] = r[r.player_id.isin(o.gsis_id)].yds.sum() / tot if tot else 0.0
        row["skill_out"] = sum(row[f"{pg.lower()}_out"] for pg in SKILL)
        res.append(row)
    return pd.DataFrame(res)


def skill_out_all() -> pd.DataFrame:
    cur = data.current_season()
    path = data.RAW / "skill_out.csv"
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["season"])
    if not set(range(2009, cur)) <= set(old.season.unique()):
        old = skill_out(range(2009, cur))
        old.to_csv(path, index=False)
    new = skill_out([cur - 1, cur])
    return pd.concat([old[old.season < cur], new[new.season == cur]], ignore_index=True)


COMP_COLS = ["game_id", "posteam", "play_type", "epa", "success", "wp", "yards_gained", "pass", "rush"]


def _comp_season(s: int) -> pd.DataFrame | None:
    """Per (game_id, team) offense on COMPETITIVE plays only: win probability 10-90% (no garbage
    time), each play's EPA capped at +/-3 so one return or long bomb cannot dominate the game."""
    path = data.RAW / "pbp_comp" / f"{s}.csv"
    if path.exists() and s < data.current_season():
        return pd.read_csv(path)
    tmp = data._fetch(f"{data.RELEASE}/pbp/play_by_play_{s}.csv.gz", data.RAW / f"pbp_comp_tmp{s}.csv.gz", refresh=True)
    if tmp is None:
        return None
    d = pd.read_csv(tmp, usecols=lambda c: c in COMP_COLS, low_memory=False)
    tmp.unlink()
    d = d[d.posteam.notna() & d.play_type.isin(["pass", "run"]) & d.epa.notna() & d.wp.between(0.10, 0.90)]
    d["epa"] = d.epa.clip(-3, 3)
    d["explosive"] = ((d["pass"] == 1) & (d.yards_gained >= 20)) | ((d["rush"] == 1) & (d.yards_gained >= 10))
    out = d.groupby(["game_id", "posteam"]).agg(c_epa=("epa", "mean"), c_sr=("success", "mean"),
                                               c_explosive=("explosive", "mean")).reset_index().rename(columns={"posteam": "team"})
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def competitive(seasons) -> pd.DataFrame:
    return pd.concat([f for s in seasons if (f := _comp_season(s)) is not None], ignore_index=True)
