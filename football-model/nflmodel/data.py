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

import numpy as np
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


PBP_COLS = ["game_id", "posteam", "defteam", "epa", "success", "play_type", "interception",
            "fumble_lost", "yards_gained", "pass", "rush", "sack", "qb_hit", "qb_dropback", "wp",
            "down", "half_seconds_remaining", "game_seconds_remaining", "no_huddle", "pass_oe",
            "drive", "drive_inside20", "fixed_drive_result", "field_goal_result", "special_teams_play"]
PBP_VERSION = 2   # bump when the per-team-game summary below gains columns


def _summarize_pbp(d: pd.DataFrame) -> pd.DataFrame:
    """Per (game_id, team-on-offense) summary of one season of play-by-play."""
    d = d[d["posteam"].notna()].copy()
    key = ["game_id", "posteam"]
    scrim = d[d["play_type"].isin(["pass", "run"]) & d["epa"].notna()].copy()
    scrim["explosive"] = ((scrim["pass"] == 1) & (scrim["yards_gained"] >= 20)) | (
        (scrim["rush"] == 1) & (scrim["yards_gained"] >= 10))
    neutral = scrim[scrim["down"].isin([1, 2]) & scrim["wp"].between(0.2, 0.8)
                    & (scrim["half_seconds_remaining"] > 120)].copy()
    # Pace: seconds between snaps within a drive, neutral situations only.
    neutral["gap"] = neutral.groupby(["game_id", "drive"])["game_seconds_remaining"].diff(-1)
    out = scrim.groupby(key).agg(epa=("epa", "mean"), sr=("success", "mean"), plays=("epa", "size"),
                                 explosive=("explosive", "mean"), dropbacks=("qb_dropback", "sum"),
                                 sacks=("sack", "sum"), qb_hits=("qb_hit", "sum"))
    nt = neutral.groupby(key).agg(neutral_pass=("qb_dropback", "mean"), pass_oe=("pass_oe", "mean"),
                                  no_huddle=("no_huddle", "mean"),
                                  sec_per_play=("gap", lambda g: g[(g > 0) & (g < 60)].median()))
    give = d.assign(g=d["interception"].fillna(0) + d["fumble_lost"].fillna(0)).groupby(key)["g"].sum()
    drives = d.groupby(key + ["drive"]).agg(rz=("drive_inside20", "max"), res=("fixed_drive_result", "first"))
    drives["rz_td"] = drives["res"].eq("Touchdown")
    rz = drives[drives["rz"] == 1].groupby(level=[0, 1])["rz_td"].agg(["sum", "size"])
    st = d[d["special_teams_play"] == 1].groupby(key)["epa"].sum()
    fg = d[d["field_goal_result"].notna()].assign(made=lambda x: x["field_goal_result"].eq("made"))
    fg = fg.groupby(key)["made"].agg(["sum", "size"])
    out = out.join(nt).assign(
        giveaways=give, drives=d.groupby(key)["drive"].nunique(),
        rz_trips=rz["size"], rz_tds=rz["sum"], st_epa=st, fg_made=fg["sum"], fg_att=fg["size"])
    fill = ["rz_trips", "rz_tds", "st_epa", "fg_made", "fg_att", "giveaways"]
    out[fill] = out[fill].fillna(0)
    return out.reset_index().rename(columns={"posteam": "team"})


def _team_game_pbp(season: int, refresh: bool) -> pd.DataFrame | None:
    """Per (game_id, team) offensive summary for one season, cached after aggregation.

    The raw season file (~20 MB) is summarized once and only the summary is kept.
    """
    path = RAW / f"pbp_team_v{PBP_VERSION}" / f"{season}.csv"
    live = season >= current_season()
    if path.exists() and not refresh:
        age_h = (time.time() - path.stat().st_mtime) / 3600
        if not live or age_h < STALE_HOURS:
            return pd.read_csv(path)
    tmp = _fetch(f"{RELEASE}/pbp/play_by_play_{season}.csv.gz", RAW / "pbp_tmp.csv.gz", refresh=True)
    if tmp is None:
        return None
    raw = pd.read_csv(tmp, usecols=lambda c: c in PBP_COLS, low_memory=False)
    tmp.unlink()
    for c in PBP_COLS:
        if c not in raw:
            raw[c] = np.nan
    agg = _summarize_pbp(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    agg.to_csv(path, index=False)
    return agg


def load_team_pbp(seasons, refresh: bool = False) -> pd.DataFrame:
    frames = [f for s in seasons if (f := _team_game_pbp(s, refresh)) is not None]
    return pd.concat(frames, ignore_index=True)


def load_rosters(seasons, refresh: bool = False) -> pd.DataFrame:
    """Each team's earliest available weekly roster per season (season, team, pfr_id, full_name).

    The season-opening roster is what roster continuity is measured from.
    """
    frames = []
    for s in seasons:
        path = RAW / "rosters" / f"{s}.csv"
        live = s >= current_season()
        fresh = path.exists() and not refresh and (
            not live or (time.time() - path.stat().st_mtime) / 3600 < STALE_HOURS)
        if not fresh:
            tmp = _fetch(f"{RELEASE}/weekly_rosters/roster_weekly_{s}.csv",
                         RAW / "roster_tmp.csv", refresh=True)
            if tmp is None:
                continue
            r = pd.read_csv(tmp, usecols=["season", "team", "week", "game_type", "status", "pfr_id",
                                                "full_name"],
                            low_memory=False)
            tmp.unlink()
            r = r[(r["game_type"] == "REG") & (r["status"] == "ACT")]
            first = r.groupby("team")["week"].transform("min")
            r = r[r["week"] == first][["season", "team", "pfr_id", "full_name"]].drop_duplicates()
            path.parent.mkdir(parents=True, exist_ok=True)
            r.to_csv(path, index=False)
        frames.append(pd.read_csv(path))
    return pd.concat(frames, ignore_index=True)


def load_game_weather(seasons, refresh: bool = False) -> pd.DataFrame:
    """Per-game weather description from play-by-play, e.g. "Light Rain Temp: 45° F, Wind: SW 12 mph".

    games.csv has temperature and wind but no precipitation; this text does.
    """
    frames = []
    for s in seasons:
        path = RAW / "pbp_weather" / f"{s}.csv"
        live = s >= current_season()
        fresh = path.exists() and not refresh and (
            not live or (time.time() - path.stat().st_mtime) / 3600 < STALE_HOURS)
        if not fresh:
            tmp = _fetch(f"{RELEASE}/pbp/play_by_play_{s}.csv.gz", RAW / "pbp_tmp.csv.gz", refresh=True)
            if tmp is None:
                continue
            w = pd.read_csv(tmp, usecols=["game_id", "weather"], low_memory=False)
            tmp.unlink()
            w = w.dropna().drop_duplicates("game_id")
            path.parent.mkdir(parents=True, exist_ok=True)
            w.to_csv(path, index=False)
        frames.append(pd.read_csv(path))
    return pd.concat(frames, ignore_index=True)


NFELO_URL = "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/nfelo_games.csv"
NFELO_TEAMS = {"LAR": "LA", "OAK": "LV", "SD": "LAC", "STL": "LA"}


def load_nfelo(refresh: bool = False) -> pd.DataFrame:
    """nfelo (greerreNFL/nfelo) pre-game ratings, QB adjustments and opening lines, 2009+.

    Adds what nflverse lacks: the opening spread (so line movement) and an independent
    Elo/QB model. Keyed here by season, week and current franchise codes.
    """
    path = _fetch(NFELO_URL, RAW / "nfelo_games.csv", refresh, live=True)
    d = pd.read_csv(path, low_memory=False)
    parts = d["game_id"].str.split("_", expand=True)
    d["season"], d["week"] = parts[0].astype(int), parts[1].astype(int)
    d["away_fr"] = parts[2].replace(NFELO_TEAMS)
    d["home_fr"] = parts[3].replace(NFELO_TEAMS)
    return d


WEATHER_BRANCH = "nfl-weather"   # written by .github/workflows/nfl-weather.yml


def load_forecasts() -> pd.DataFrame:
    """Latest kickoff forecasts saved by the GitHub weather job (empty if unavailable)."""
    import io
    import subprocess

    repo = ROOT.parent
    try:
        subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin", WEATHER_BRANCH],
                       check=True, capture_output=True, timeout=120)
        csv = subprocess.run(["git", "-C", str(repo), "show", f"origin/{WEATHER_BRANCH}:weather.csv"],
                             check=True, capture_output=True, text=True, timeout=60).stdout
        return pd.read_csv(io.StringIO(csv))
    except (subprocess.SubprocessError, OSError, pd.errors.EmptyDataError):
        return pd.DataFrame()
