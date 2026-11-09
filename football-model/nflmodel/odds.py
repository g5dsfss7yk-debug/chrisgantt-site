"""Live odds from The Odds API (api.the-odds-api.com): DraftKings' price next to sharper books.

The edge that actually beats a sportsbook is price, not prediction: when DraftKings pays more
than the sharp books' fair (no-vig) price for the same bet, DraftKings is off. This module
fetches one game's ladder props (and game lines) from DraftKings plus Pinnacle, FanDuel and
others, and returns each DK leg with the other books' fair chance for the same player, market
and number.

The key goes in the URL (the API has no header option), so it is read from the environment
variable ODDS_API_KEY, which the user sets in the environment's settings. Each call costs
credits from the free monthly quota (about 500): one game's props are a few credits; responses
are cached for 10 minutes in data/raw/odds/.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from nflmodel.data import RAW

API = "https://api.the-odds-api.com/v4"
CACHE = RAW / "odds"
SPORT = {"nfl": "americanfootball_nfl", "cfb": "americanfootball_ncaaf"}
# DraftKings plus the books whose prices are used as the fair line (Pinnacle is the sharpest).
BOOKS = "draftkings,pinnacle,fanduel,betmgm,williamhill_us,betonlineag,lowvig"
SHARP = ("pinnacle", "lowvig", "betonlineag", "fanduel", "betmgm", "williamhill_us")
# Ladder ("X+") markets DraftKings offers, mapped to the model's markets.
PROP_MARKETS = {
    "player_pass_yds_alternate": "passing_yards",
    "player_rush_yds_alternate": "rushing_yards",
    "player_reception_yds_alternate": "receiving_yards",
    "player_pass_yds": "passing_yards",
    "player_rush_yds": "rushing_yards",
    "player_reception_yds": "receiving_yards",
    "player_anytime_td": "anytime_td",
}


def key() -> str | None:
    # DDS_API_KEY: the name as first saved in the environment settings (the O was dropped)
    return os.environ.get("ODDS_API_KEY") or os.environ.get("DDS_API_KEY")


TTL = 600  # seconds a cached response is reused (live betting sets this lower)


def _get(path: str, **params) -> object:
    k = key()
    if not k:
        raise RuntimeError("ODDS_API_KEY is not set (add it in the environment's settings)")
    CACHE.mkdir(parents=True, exist_ok=True)
    tag = path.strip("/").replace("/", "_") + "_" + "_".join(f"{a}-{b}" for a, b in sorted(params.items()))
    f = CACHE / (tag[:180] + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < TTL:
        return json.loads(f.read_text())
    url = f"{API}{path}?" + urllib.parse.urlencode({**params, "apiKey": k})
    with urllib.request.urlopen(url, timeout=30) as r:
        left = r.headers.get("x-requests-remaining")
        body = r.read()
    if left is not None:
        print(f"odds API: {left} credits left this month")
    f.write_bytes(body)
    return json.loads(body)


def events(league: str = "nfl") -> pd.DataFrame:
    ev = _get(f"/sports/{SPORT[league]}/events")
    return pd.DataFrame([{"id": e["id"], "home": e["home_team"], "away": e["away_team"],
                          "kickoff": e["commence_time"]} for e in ev])


def find_event(league: str, team: str) -> str | None:
    """Event id for the next game of a team (full name or a word of it, e.g. 'Bears')."""
    ev = events(league)
    t = team.lower()
    hit = ev[ev["home"].str.lower().str.contains(t) | ev["away"].str.lower().str.contains(t)]
    return None if hit.empty else hit.sort_values("kickoff")["id"].iloc[0]


def implied(price: float) -> float:
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)


def props(league: str, event_id: str) -> pd.DataFrame:
    """One row per book, player, market, side and number, with the book's no-vig chance where the
    book also prices the other side (Over/Under, Yes/No)."""
    d = _get(f"/sports/{SPORT[league]}/events/{event_id}/odds", bookmakers=BOOKS,
             markets=",".join(PROP_MARKETS), oddsFormat="american")
    rows = []
    for b in d.get("bookmakers", []):
        for m in b["markets"]:
            for o in m["outcomes"]:
                rows.append({"book": b["key"], "market": PROP_MARKETS.get(m["key"], m["key"]),
                             "ladder": m["key"].endswith("_alternate"), "player": o.get("description", ""),
                             "side": o["name"], "point": o.get("point", np.nan), "price": o["price"]})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["implied"] = df["price"].map(implied)
    # pair Over with Under inside the same raw market: a book's main line and its alternate ladder
    # can share a number, and pooling them would put three prices in one pair
    g = ["book", "market", "ladder", "player", "point"]
    pair = df.groupby(g)["implied"].transform("sum")
    two = (df.groupby(g)["side"].transform("nunique") == 2) & (df.groupby(g)["side"].transform("size") == 2)
    df["fair"] = np.where(two, df["implied"] / pair, np.nan)
    return df


def compare(df: pd.DataFrame) -> pd.DataFrame:
    """Each DraftKings Over/Yes leg with the sharp books' fair chance for the same bet.
    For a DK ladder 'X+' (Over X-0.5) without an exact match, the fair chance comes from the
    sharp books' main line only when it is the same number."""
    if df.empty:
        return df
    dk = df[(df["book"] == "draftkings") & df["side"].isin(["Over", "Yes"])].copy()
    # the same DK leg can be listed in both the main and the alternate market: keep the better price
    dk = dk.sort_values("price", ascending=False).drop_duplicates(["market", "player", "point"])
    sharp = df[df["book"].isin(SHARP) & df["side"].isin(["Over", "Yes"]) & df["fair"].notna()]
    fair = sharp.groupby(["market", "player", "point"], dropna=False).agg(
        sharp_fair=("fair", "mean"), sharp_books=("book", lambda s: ",".join(sorted(set(s)))))
    dk = dk.merge(fair, on=["market", "player", "point"], how="left")
    dk["dk_implied"] = dk["implied"]
    dk["edge_vs_sharp"] = dk["sharp_fair"] - dk["dk_implied"]
    return dk[["player", "market", "point", "price", "dk_implied", "sharp_fair", "sharp_books", "edge_vs_sharp"]]


def ladders(league: str, team: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(DraftKings Over/Yes rungs, sharp main lines) for one team's next game.
    Sharp main line = per player and market, the sharp books' two-sided number closest to 50/50,
    with its average no-vig Over chance."""
    ev = find_event(league, team)
    if ev is None:
        raise SystemExit(f"no upcoming {league} game found for {team}")
    df = props(league, ev)
    if df.empty:
        return df, df
    dk = df[(df["book"] == "draftkings") & df["side"].isin(["Over", "Yes"])]
    dk = dk.sort_values("price", ascending=False).drop_duplicates(["market", "player", "point"])
    sh = df[df["book"].isin(SHARP) & df["side"].isin(["Over", "Yes"]) & df["fair"].notna()]
    sh = sh.groupby(["market", "player", "point"], dropna=False).agg(fair=("fair", "mean"), books=("book", "nunique")).reset_index()
    sh = sh.assign(off=(sh["fair"] - 0.5).abs()).sort_values("off").drop_duplicates(["market", "player"])
    return dk, sh.drop(columns="off")


def parlay_ev(legs: list[tuple[float, float]], boost: float = 0.0) -> tuple[float, float, float]:
    """legs = [(win chance, American price)]; boost = profit boost (0.30 = +30%).
    Returns (parlay chance, decimal payout incl. boost, expected return per $1)."""
    p, dec = 1.0, 1.0
    for q, price in legs:
        p *= q
        dec *= 1 + (price / 100 if price > 0 else 100 / -price)
    pay = 1 + (dec - 1) * (1 + boost)
    return p, pay, p * pay - 1
