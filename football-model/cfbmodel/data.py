"""Download and cache public college football data from sportsdataverse.

Sources (all free, no API key):
  schedules  - cfbfastR-data: every FBS game, scores, neutral site, conference, CFBD Elo
  betting    - cfbfastR-data: opening and current lines from several books (2006-2025)
  pbp        - sportsdataverse-data espn_cfb_pbp release: play-by-play with EPA, reduced to
               one row per team-game (cached as small CSVs, the parquet is not kept)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from nflmodel.data import ROOT, _fetch

RAW = ROOT / "data" / "raw" / "cfb"
REPO = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main"
PBP_URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_pbp"
FIRST_SEASON = 2014
PBP_VERSION = 1

PBP_COLS = ["game_id", "season", "week", "pos_team_id", "def_pos_team_id", "period",
            "pos_score_diff_start", "scrimmage_play", "kneel_down", "EPA", "EPA_success",
            "EPA_explosive", "pass", "rush", "havoc", "sack", "turnover_vec", "rz_play",
            "drive.id", "touchdown", "passer_player_name", "homeTeamId", "homeTeamSpread",
            "overUnder", "fg_attempt", "fg_made", "EPA_fg", "EPA_punt", "EPA_kickoff"]


def current_season() -> int:
    today = dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


def load_schedules(refresh: bool = False) -> pd.DataFrame:
    out = []
    for s in range(FIRST_SEASON, current_season() + 1):
        live = s == current_season()
        path = _fetch(f"{REPO}/schedules/csv/cfb_schedules_{s}.csv", RAW / f"schedules_{s}.csv",
                      refresh, live=live)
        out.append(pd.read_csv(path, low_memory=False))
    g = pd.concat(out, ignore_index=True)
    g["start"] = pd.to_datetime(g["start_date"], utc=True)
    # Kickoff in US Eastern for display and for the game date.
    g["kickoff_et"] = g["start"].dt.tz_convert("America/New_York")
    g["gameday"] = g["kickoff_et"].dt.tz_localize(None).dt.normalize()
    g["result"] = g["home_points"] - g["away_points"]
    g["total"] = g["home_points"] + g["away_points"]
    g.loc[~g["completed"].astype(bool), ["result", "total"]] = np.nan
    return g.sort_values("start").reset_index(drop=True)


def load_lines(refresh: bool = False) -> pd.DataFrame:
    """Opening and latest spread/total per game, as the median across books.

    The book file lists each team's spread under abbreviations that don't match any other
    source, so each row's side is found by matching its current number to ESPN's line for
    the home team. spread_* is the home team's expected margin.
    """
    out = RAW / "lines.csv"
    src = _fetch(f"{REPO}/betting/csv/cfb_line_odds.csv.gz", RAW / "cfb_line_odds.csv.gz", refresh, live=True)
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return pd.read_csv(out)
    b = pd.read_csv(src, low_memory=False).drop_duplicates()
    b = b[b["season"] >= FIRST_SEASON]
    espn = load_team_games()[["game_id", "espn_spread"]].drop_duplicates("game_id")
    sp = b[b["market_type"] == "spread"].merge(espn, on="game_id")
    sp = sp[sp["lines"].notna() & (sp["lines"] != 0) & sp["espn_spread"].notna()]
    is_home = (sp["lines"] + sp["espn_spread"]).abs() < (sp["lines"] - sp["espn_spread"]).abs()
    sign = np.where(is_home, -1.0, 1.0)  # a -7 line on the home team = home by 7
    sp = sp.assign(open=sp["opening_lines"].replace(0, np.nan) * sign, now=sp["lines"] * sign)
    sp = sp.groupby("game_id")[["open", "now"]].median().add_prefix("spread_")
    tot = b[b["market_type"] == "total"].replace({"opening_lines": {0: np.nan}}).groupby("game_id")[["opening_lines", "lines"]].median()
    tot.columns = ["total_open", "total_now"]
    lines = sp.join(tot, how="outer").reset_index()
    lines.to_csv(out, index=False)
    return lines


def _garbage(p: pd.DataFrame) -> pd.Series:
    """Plays in clear garbage time (by quarter and score margin)."""
    d = p["pos_score_diff_start"].abs()
    return ((p["period"] == 2) & (d > 38)) | ((p["period"] == 3) & (d > 28)) | ((p["period"] >= 4) & (d > 22))


def _summarize_pbp(p: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, offense): efficiency, style, red zone, special teams, starting QB."""
    keys = ["game_id", "pos_team_id"]
    scrim = p[p["scrimmage_play"].astype(bool) & ~p["kneel_down"].astype(bool) & p["EPA"].notna()]
    live = scrim[~_garbage(scrim)]
    agg = live.groupby(keys).agg(
        epa=("EPA", "mean"), sr=("EPA_success", "mean"), explosive=("EPA_explosive", "mean"),
        pass_rate=("pass", "mean"), havoc=("havoc", "mean"), sack=("sack", "mean"),
        plays_live=("EPA", "size"), opp=("def_pos_team_id", "first"))
    allp = scrim.groupby(keys).agg(plays=("EPA", "size"), giveaways=("turnover_vec", "sum"))
    # Red zone: drives that reached the 20, and how many ended in a touchdown.
    rz = scrim[scrim["rz_play"].astype(bool)].groupby(keys + ["drive.id"])["touchdown"].max()
    rz = rz.astype(float).groupby(keys).agg(rz_trips="size", rz_tds="sum")
    st = p.assign(st=p[["EPA_fg", "EPA_punt", "EPA_kickoff"]].fillna(0).sum(axis=1)).groupby(keys).agg(
        st_epa=("st", "sum"), fg_att=("fg_attempt", "sum"), fg_made=("fg_made", "sum"))
    qb = (p.dropna(subset=["passer_player_name"]).groupby(keys)["passer_player_name"]
          .agg(lambda s: s.value_counts().index[0]).rename("qb"))
    out = agg.join([allp, rz, st, qb], how="left").reset_index()
    out[["rz_trips", "rz_tds"]] = out[["rz_trips", "rz_tds"]].fillna(0)
    return out.rename(columns={"pos_team_id": "team_id"})


def _game_meta(p: pd.DataFrame) -> pd.DataFrame:
    """ESPN's line for each game (the latest one before kickoff) and the home abbreviation."""
    return p.groupby("game_id").agg(home_id=("homeTeamId", "first"), espn_spread=("homeTeamSpread", "first"),
                                    espn_total=("overUnder", "first")).reset_index()


def load_team_games(refresh: bool = False) -> pd.DataFrame:
    """Per team-game play-by-play summaries for every season, plus ESPN's game lines."""
    out = []
    for s in range(FIRST_SEASON, current_season() + 1):
        path = RAW / f"pbp_team_v{PBP_VERSION}" / f"{s}.csv"
        live = s == current_season()
        fresh = path.exists() and not refresh and (
            not live or (dt.datetime.now().timestamp() - path.stat().st_mtime) / 3600 < 6)
        if not fresh:
            raw = _fetch(f"{PBP_URL}/play_by_play_{s}.parquet", RAW / f"pbp_{s}.parquet", True)
            p = pd.read_parquet(raw, columns=PBP_COLS + ["homeTeamAbbrev"])
            team = _summarize_pbp(p).merge(_game_meta(p), on="game_id")
            team = team.merge(p.groupby("game_id")["homeTeamAbbrev"].first().rename("home_abbr"), on="game_id")
            team["season"] = s
            path.parent.mkdir(parents=True, exist_ok=True)
            team.to_csv(path, index=False)
            raw.unlink()
        out.append(pd.read_csv(path))
    tg = pd.concat(out, ignore_index=True)
    tg["rz_tds"] = tg["rz_tds"].replace({"True": 1, "False": 0}).astype(float)
    return tg
