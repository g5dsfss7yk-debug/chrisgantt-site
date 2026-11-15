"""Audit E: the model against DraftKings' REAL prices. This is the test that decides whether a
model edge is worth betting (audits A-D only checked the model's chances, not its picks against
the book).

Input: every DK ladder rung saved by `run.py props --scan ...` (picks/rungs/*.csv): the model's
chance, the sharp-anchored chance and DK's price, captured before kickoff. Each rung is graded
from ESPN's box score. Report: for each size of edge, how often the rungs hit, against what the
model and DK said, and the profit of a flat $1 on each at DK's price.

    python audit/vs_dk.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd

import recs
from nflmodel import data

RUNGS = data.ROOT / "picks" / "rungs"
STAT = {"rushing_yards": ("rushing", "YDS"), "receiving_yards": ("receiving", "YDS"), "passing_yards": ("passing", "YDS")}


def load() -> pd.DataFrame:
    files = sorted(RUNGS.glob("*.csv"))
    if not files:
        raise SystemExit("no saved rungs yet: run `run.py props --week N --scan all` before games")
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    d = d[d["pregame"].astype(str) == "True"]
    # the last price seen before kickoff for each rung (closest to what you could bet)
    return d.sort_values("snapshot_utc").drop_duplicates(["game_id", "player", "market", "rung"], keep="last")


def grade(d: pd.DataFrame) -> pd.DataFrame:
    games = data.load_games().set_index("game_id")
    out = []
    for gid, g in d.groupby("game_id"):
        if gid not in games.index or pd.isna(games.at[gid, "result"]):
            continue  # not final yet
        day = games.at[gid, "gameday"]
        events = recs._events("nfl", day)
        for (player, market), h in g.groupby(["player", "market"]):
            s = recs._player_stats("nfl", events, player)
            val = 0.0 if s is None else float(str(s.get(STAT[market], "0")).split("/")[0] or 0)
            # a player with no box-score line at all may not have played: DK voids those, so drop them
            if s is None:
                continue
            out.append(h.assign(actual=val, hit=val >= h["rung"]))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def report(r: pd.DataFrame):
    r = r.assign(dec=np.where(r["price"] > 0, 1 + r["price"] / 100, 1 + 100 / -r["price"]))
    r["profit"] = np.where(r["hit"], r["dec"] - 1, -1.0)
    r["edge"] = r["model"] - r["dk"]
    print(f"{len(r)} graded DK rungs from {r['game_id'].nunique()} games\n")

    def table(col, label):
        b = pd.cut(r[col], [-1, 0, 0.03, 0.06, 0.10, 1], labels=["<0", "0-3%", "3-6%", "6-10%", "10%+"])
        t = r.groupby(b, observed=True).agg(n=("hit", "size"), model=("model", "mean"), dk=("dk", "mean"),
                                            hit=("hit", "mean"), profit_per_1=("profit", "mean"))
        print(f"by {label}:\n{t.round(3).to_string()}\n")

    table("edge", "model edge (model chance - DK implied)")
    if r["sharp"].notna().any():
        rs = r[r["sharp"].notna()].assign(edge_s=lambda x: x["sharp"] - x["dk"])
        b = pd.cut(rs["edge_s"], [-1, 0, 0.03, 1], labels=["<0", "0-3%", "3%+"])
        print("by sharp edge:\n" + rs.groupby(b, observed=True).agg(
            n=("hit", "size"), sharp=("sharp", "mean"), dk=("dk", "mean"), hit=("hit", "mean"),
            profit_per_1=("profit", "mean")).round(3).to_string() + "\n")
    bet = r[(r["edge"] >= 0.03) & (r["model"] >= 0.70)]
    print(f"THE BET RULE (model 70%+ and 3%+ over DK): {len(bet)} rungs, hit {bet['hit'].mean():.0%}"
          f" (model said {bet['model'].mean():.0%}, DK {bet['dk'].mean():.0%}), profit {bet['profit'].mean():+.1%} per $1"
          if len(bet) else "THE BET RULE: no graded rungs yet")
    print("\nRungs of one player are linked (if he gets 80, every rung under 80 hits), so the real sample is"
          " closer to the number of player-games than the number of rungs. Judge after 2-3 weeks.")


if __name__ == "__main__":
    g = grade(load())
    if g.empty:
        raise SystemExit("no saved rungs from finished games yet")
    report(g)
