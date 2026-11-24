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


PX_COLS = ["game_id", "posteam", "defteam", "play_type", "fumble", "fumble_lost", "rusher_player_id",
           "receiver_player_id", "yardline_100", "two_point_attempt", "fumble_recovery_1_team"]


def _px_season(s: int):
    """One pass over a season's play-by-play: (team fumbles and how many were lost, per game) and
    (each player's red-zone and goal-line touches, per game)."""
    tp, pp = data.RAW / "pbp_fum" / f"{s}.csv", data.RAW / "pbp_rz" / f"{s}.csv"
    if tp.exists() and pp.exists() and s < data.current_season():
        return pd.read_csv(tp), pd.read_csv(pp)
    tmp = data._fetch(f"{data.RELEASE}/pbp/play_by_play_{s}.csv.gz", data.RAW / f"pbp_px_tmp{s}.csv.gz", refresh=True)
    if tmp is None:
        return None, None
    d = pd.read_csv(tmp, usecols=lambda c: c in PX_COLS, low_memory=False)
    tmp.unlink()
    d = d[d.posteam.notna()]
    f = d[d.fumble == 1].groupby(["game_id", "posteam"]).agg(fumbles=("fumble", "sum"), fum_lost=("fumble_lost", "sum"))
    f = f.reset_index().rename(columns={"posteam": "team"})
    sc = d[d.play_type.isin(["run", "pass"]) & (d.two_point_attempt != 1)]
    rows = []
    for col in ("rusher_player_id", "receiver_player_id"):
        x = sc[sc[col].notna()]
        rows.append(pd.DataFrame({"game_id": x.game_id, "team": x.posteam, "player_id": x[col],
                                  "rz": (x.yardline_100 <= 20).astype(int), "gl": (x.yardline_100 <= 5).astype(int)}))
    r = pd.concat(rows).groupby(["game_id", "team", "player_id"], as_index=False)[["rz", "gl"]].sum()
    tot = r.groupby(["game_id", "team"])[["rz", "gl"]].transform("sum")
    r["rz_share"], r["gl_share"] = r.rz / tot.rz.where(tot.rz > 0), r.gl / tot.gl.where(tot.gl > 0)
    for p, x in ((tp, f), (pp, r)):
        p.parent.mkdir(parents=True, exist_ok=True); x.to_csv(p, index=False)
    return f, r


def pbp_extra(seasons):
    a, b = zip(*[_px_season(s) for s in seasons])
    return pd.concat([x for x in a if x is not None]), pd.concat([x for x in b if x is not None])


# home time zone (hours behind Eastern) by the code the schedule used that season
TZ = {**{t: 0 for t in "BUF MIA NE NYJ BAL CIN CLE PIT JAX IND NYG PHI WAS DET ATL CAR TB".split()},
      **{t: 1 for t in "CHI GB MIN TEN HOU DAL NO KC STL".split()},
      **{t: 2 for t in "DEN ARI".split()}, **{t: 3 for t in "LV OAK LAC SD LA SF SEA".split()}}


def game_extras(d: pd.DataFrame) -> pd.DataFrame:
    """Per game (index of d): close-game luck, time zones, division, byes, coach tenure."""
    d = d.sort_values(["gameday", "gametime"])
    out = pd.DataFrame(index=d.index)
    # close-game luck: season-to-date wins minus half of games decided by 8 or fewer
    rec, cl_h, cl_a = {}, [], []
    tenure, ten_h, ten_a, newc_h, newc_a = {}, [], [], [], []
    first = {}
    for r in d.itertuples():
        for side, t, lst in (("home", r.home_fr, cl_h), ("away", r.away_fr, cl_a)):
            lst.append(rec.get((r.season, t), 0.0))
        for side, t, coach, tl, nl in (("home", r.home_fr, r.home_coach, ten_h, newc_h), ("away", r.away_fr, r.away_coach, ten_a, newc_a)):
            tl.append(np.log1p(tenure.get((t, coach), 0)))
            first.setdefault((t, coach), r.season)
            nl.append(int(first[(t, coach)] == r.season))
        if pd.notna(r.result) and abs(r.result) <= 8:
            w = 0.5 if r.result == 0 else float(r.result > 0)
            rec[(r.season, r.home_fr)] = rec.get((r.season, r.home_fr), 0.0) + (w - 0.5)
            rec[(r.season, r.away_fr)] = rec.get((r.season, r.away_fr), 0.0) + (0.5 - w)
        if pd.notna(r.result):
            for t, coach in ((r.home_fr, r.home_coach), (r.away_fr, r.away_coach)):
                tenure[(t, coach)] = tenure.get((t, coach), 0) + 1
    out["home_close_luck"], out["away_close_luck"] = cl_h, cl_a
    out["home_tenure"], out["away_tenure"], out["home_new_coach"], out["away_new_coach"] = ten_h, ten_a, newc_h, newc_a
    neutral = d.location.eq("Neutral")
    tzh, tza = d.home_team.map(TZ).fillna(0), d.away_team.map(TZ).fillna(0)
    out["tz_diff"] = (tza - tzh).abs().where(~neutral, 0)                    # hours the away team moved
    out["west_early"] = ((tza - tzh >= 2) & (d.gametime.astype(str) <= "13:05") & ~neutral).astype(int)
    out["div"] = d.div_game.fillna(0)
    out["home_bye"], out["away_bye"] = (d.home_rest >= 13).astype(int), (d.away_rest >= 13).astype(int)
    return out.loc[d.index]


def returning_snaps() -> pd.DataFrame:
    """Per (season, team): share of LAST season's offensive / defensive snaps by players on this
    season's opening roster (same team) - how much of the team came back."""
    sn = data.load_snaps(range(2013, data.current_season() + 1))
    sn["team"] = sn.team.map(teams.franchise)
    ro = data.load_rosters(range(2014, data.current_season() + 1))
    ro["team"] = ro.team.map(teams.franchise)
    tot = sn.groupby(["season", "team", "pfr_player_id"], as_index=False)[["offense_snaps", "defense_snaps"]].sum()
    rows = []
    for (season, team), r in ro.groupby(["season", "team"]):
        last = tot[(tot.season == season - 1) & (tot.team == team)]
        if last.empty:
            continue
        back = last[last.pfr_player_id.isin(r.pfr_id)]
        rows.append((season, team, back.offense_snaps.sum() / max(last.offense_snaps.sum(), 1),
                     back.defense_snaps.sum() / max(last.defense_snaps.sum(), 1)))
    return pd.DataFrame(rows, columns=["season", "team", "ret_off", "ret_def"])


def ol_out(seasons) -> pd.DataFrame:
    """Per (season, week, team): offensive linemen who played half the snaps in one of the team's
    last 2 games and are listed Out/Doubtful that week."""
    import re
    key = lambda n: re.sub(r"[^a-z]", "", re.sub(r"\s+(jr|sr|ii|iii|iv)\.?$", "", str(n).lower()))
    sn = data.load_snaps(seasons)
    sn = sn[sn.position.isin(["T", "G", "C", "OT", "OG", "OL"]) & (sn.offense_pct >= 0.5)].copy()
    sn["team"], sn["k"] = sn.team.map(teams.franchise), sn.player.map(key)
    inj = pd.concat([d for s in seasons if (d := _release("injuries", f"injuries_{s}.csv", s)) is not None])
    inj = inj[inj.report_status.isin(["Out", "Doubtful"]) & inj.position.isin(["T", "G", "C", "OT", "OG", "OL"])].copy()
    inj["team"], inj["k"] = inj.team.map(teams.franchise), inj.full_name.map(key)
    tw = sn[["season", "week", "team"]].drop_duplicates().sort_values(["team", "season", "week"])
    res = []
    for (season, week, team), o in inj.groupby(["season", "week", "team"]):
        prev = tw[(tw.team == team) & ((tw.season < season) | ((tw.season == season) & (tw.week < week)))].tail(2)
        if prev.empty:
            continue
        reg = set(sn.merge(prev, on=["season", "week", "team"]).k)
        res.append((season, week, team, len(reg & set(o.k))))
    return pd.DataFrame(res, columns=["season", "week", "team", "ol_out"])
