"""Download kickoff-window forecasts for upcoming outdoor NFL and college games from Open-Meteo.

Run by .github/workflows/nfl-weather.yml on GitHub's runners (the model's cloud
sandbox cannot reach weather APIs). Writes one row per game:
  game_id, temp, wind, gust, precip_prob, precip_in, snow_in, fetched_at
College rows have game_id "cfb_<ESPN id>" plus the stadium's surface (grass true/false).

  python scripts/fetch_weather.py OUT.csv [--days 8]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nflmodel import teams  # noqa: E402

GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
CFB = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main"
API = "https://api.open-meteo.com/v1/forecast"
GAME_HOURS = 4  # kickoff hour plus the next three

# International / neutral venues by nflverse stadium_id (lat, lon).
NEUTRAL = {
    "LON00": (51.556, -0.280), "LON01": (51.456, -0.341), "LON02": (51.604, -0.066),
    "MEX00": (19.303, -99.150), "GER00": (48.219, 11.625), "MUN01": (48.219, 11.625),
    "FRA00": (50.069, 8.646), "MAD01": (40.453, -3.688), "SAO00": (-23.545, -46.474),
    "RIO00": (-22.912, -43.230), "DUB00": (53.361, -6.251), "MEL00": (-37.820, 144.983),
    "PAR00": (48.924, 2.360),
}


def coords(g) -> tuple[float, float] | None:
    if g.location == "Neutral":
        return NEUTRAL.get(g.stadium_id)
    st = teams.STADIUM.get(g.home_team)
    return (st[0], st[1]) if st else None


def get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except OSError:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed: {url}")


def _window(lat, lon, day, start_hour):
    d = get({"latitude": lat, "longitude": lon, "timezone": "America/New_York",
             "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch",
             "hourly": "temperature_2m,wind_speed_10m,wind_gusts_10m,"
                       "precipitation_probability,precipitation,snowfall",
             "start_date": day, "end_date": day})
    h = pd.DataFrame(d["hourly"])
    if h.empty:
        return None
    w = h.iloc[start_hour:start_hour + GAME_HOURS]
    return {"temp": round(w["temperature_2m"].mean(), 1), "wind": round(w["wind_speed_10m"].mean(), 1),
            "gust": round(w["wind_gusts_10m"].max(), 1), "precip_prob": w["precipitation_probability"].max(),
            "precip_in": round(w["precipitation"].sum(), 2), "snow_in": round(w["snowfall"].sum() / 2.54, 2),
            "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}


def college(days: int) -> list[dict]:
    """Upcoming college games at stadiums in the team-info file (outdoor ones get a forecast)."""
    season = dt.date.today().year if dt.date.today().month >= 8 else dt.date.today().year - 1
    s = pd.read_csv(f"{CFB}/schedules/csv/cfb_schedules_{season}.csv", low_memory=False)
    # Stadium coordinates and surface, saved from cfbfastR-data's team info (parquet needs pyarrow).
    venues = pd.read_csv(Path(__file__).with_name("cfb_venues.csv")).set_index("venue_id")
    s["kick"] = pd.to_datetime(s["start_date"], utc=True).dt.tz_convert("America/New_York")
    now = pd.Timestamp.now(tz="America/New_York")
    up = s[~s["completed"].astype(bool) & (s["kick"] >= now - pd.Timedelta(hours=4))
           & (s["kick"] <= now + pd.Timedelta(days=days))]
    rows = []
    for x in up.itertuples(index=False):
        v = venues.loc[x.venue_id] if x.venue_id in venues.index else None
        if v is None or pd.isna(v["latitude"]):
            continue
        row = {"game_id": f"cfb_{x.game_id}", "home_team": x.home_team, "grass": bool(v["grass"]),
               "dome": bool(v["dome"])}
        if not v["dome"]:
            w = _window(v["latitude"], v["longitude"], f"{x.kick:%Y-%m-%d}", x.kick.hour)
            if w:
                row.update(w)
        rows.append(row)
    print(f"{len(rows)} college games")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--days", type=int, default=8)
    args = ap.parse_args()

    g = pd.read_csv(GAMES_URL, low_memory=False)
    g["gameday"] = pd.to_datetime(g["gameday"])
    today = pd.Timestamp(dt.date.today())
    up = g[g["result"].isna() & (g["gameday"] >= today - pd.Timedelta(days=1))
           & (g["gameday"] <= today + pd.Timedelta(days=args.days))
           & ~g["roof"].isin(["dome", "closed"])]

    rows = []
    for x in up.itertuples(index=False):
        c = coords(x)
        if c is None:
            print(f"skip {x.game_id}: no coordinates for {x.stadium_id}")
            continue
        # nflverse gametime is US Eastern; ask for hourly data on that clock.
        d = get({"latitude": c[0], "longitude": c[1], "timezone": "America/New_York",
                 "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
                 "precipitation_unit": "inch",
                 "hourly": "temperature_2m,wind_speed_10m,wind_gusts_10m,"
                           "precipitation_probability,precipitation,snowfall",
                 "start_date": f"{x.gameday:%Y-%m-%d}", "end_date": f"{x.gameday:%Y-%m-%d}"})
        h = pd.DataFrame(d["hourly"])
        if h.empty:
            continue
        start = int(str(x.gametime or "13:00")[:2])
        w = h.iloc[start:start + GAME_HOURS]
        rows.append({
            "game_id": x.game_id, "home_team": x.home_team,
            "temp": round(w["temperature_2m"].mean(), 1),
            "wind": round(w["wind_speed_10m"].mean(), 1),
            "gust": round(w["wind_gusts_10m"].max(), 1),
            "precip_prob": w["precipitation_probability"].max(),
            "precip_in": round(w["precipitation"].sum(), 2),
            "snow_in": round(w["snowfall"].sum() / 2.54, 2),  # Open-Meteo snowfall is cm
            "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        })
        print(rows[-1])
    try:
        rows += college(min(args.days, 3))
    except Exception as e:  # college data is optional; never lose the NFL forecasts
        print(f"college weather skipped: {e}")
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"wrote {len(rows)} games to {args.out}")


if __name__ == "__main__":
    main()
