"""Download and cache public NFL data from nflverse.

Sources (all free, no API key):
  games      - schedule, scores, Vegas lines, roof/surface/temp/wind, QBs, rest
  injuries   - weekly official injury reports (2009+)
  snap_counts- per-player snap share by game (2012+), used to weight injuries
  pbp        - play-by-play (1999+), reduced to per-team-game EPA, success rate, turnovers
"""
from __future__ import annotations

import datetime as dt
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

# Files for the in-progress season change daily; re-download after this many hours.
STALE_HOURS = 6


def _fetch(url: str, path: Path, refresh: bool = False, live: bool = False) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        age_h = (time.time() - path.stat().st_mtime) / 3600
        if not live or age_h < STALE_HOURS:
            return path
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                path.write_bytes(r.read())
            return path
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except OSError as e:
            err = e
        time.sleep(2 ** attempt)
    if path.exists():  # offline: fall back to the cached copy
        print(f"warning: could not refresh {url} ({err}); using cached copy")
        return path
    raise RuntimeError(f"failed to download {url}: {err}")


def current_season() -> int:
    today = dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


def load_games(refresh: bool = False) -> pd.DataFrame:
    path = _fetch(GAMES_URL, RAW / "games.csv", refresh, live=True)
    g = pd.read_csv(path, low_memory=False)
    g["gameday"] = pd.to_datetime(g["gameday"])
    return g


def _load_release(kind: str, seasons, refresh: bool) -> pd.DataFrame:
    cur = current_season()
    frames = []
    for s in seasons:
        url = f"{RELEASE}/{kind}/{kind}_{s}.csv"
        path = _fetch(url, RAW / kind / f"{s}.csv", refresh, live=(s >= cur))
        if path is not None:
            frames.append(pd.read_csv(path, low_memory=False))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_injuries(seasons, refresh: bool = False) -> pd.DataFrame:
    df = _load_release("injuries", seasons, refresh)
    df["position"] = df["position"].astype(str).str.strip()
    return df


def load_snaps(seasons, refresh: bool = False) -> pd.DataFrame:
    return _load_release("snap_counts", seasons, refresh)


PBP_COLS = ["game_id", "posteam", "defteam", "epa", "success", "play_type",
            "interception", "fumble_lost"]


def _team_game_pbp(season: int, refresh: bool) -> pd.DataFrame | None:
    """Per (game_id, team) offensive EPA/play, success rate, plays and giveaways.

    The raw season file (~20 MB) is aggregated once and only the summary is kept.
    """
    path = RAW / "pbp_team" / f"{season}.csv"
    live = season >= current_season()
    if path.exists() and not refresh:
        age_h = (time.time() - path.stat().st_mtime) / 3600
        if not live or age_h < STALE_HOURS:
            return pd.read_csv(path)
    tmp = _fetch(f"{RELEASE}/pbp/play_by_play_{season}.csv.gz", RAW / "pbp_tmp.csv.gz", refresh=True)
    if tmp is None:
        return None
    d = pd.read_csv(tmp, usecols=PBP_COLS, low_memory=False)
    tmp.unlink()
    d["giveaway"] = d["interception"].fillna(0) + d["fumble_lost"].fillna(0)
    give = d.groupby(["game_id", "posteam"])["giveaway"].sum()
    plays = d[d["play_type"].isin(["pass", "run"]) & d["epa"].notna()]
    agg = plays.groupby(["game_id", "posteam"]).agg(
        epa=("epa", "mean"), sr=("success", "mean"), plays=("epa", "size"))
    agg["giveaways"] = give.reindex(agg.index).fillna(0)
    agg = agg.reset_index().rename(columns={"posteam": "team"})
    path.parent.mkdir(parents=True, exist_ok=True)
    agg.to_csv(path, index=False)
    return agg


def load_team_pbp(seasons, refresh: bool = False) -> pd.DataFrame:
    frames = [f for s in seasons if (f := _team_game_pbp(s, refresh)) is not None]
    return pd.concat(frames, ignore_index=True)
