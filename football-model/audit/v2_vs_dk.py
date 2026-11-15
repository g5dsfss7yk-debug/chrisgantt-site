"""Audit I: the v2 props/alt-line card against DraftKings' REAL prices.

Every DK rung that v2/props_card.py priced before kickoff is saved in picks/rungs_v2/. This grades
each one from ESPN's box score and asks the question that decides whether to bet: when v2's tested
chance is above DK's implied chance, do those rungs hit often enough to make money at DK's price?

    PYTHONPATH=. python audit/v2_vs_dk.py
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
import recs
from nflmodel import data

D = data.ROOT / "picks" / "rungs_v2"


def value(s, mk):
    f = lambda c, l: float(str(s.get((c, l), "0") or 0).split("/")[0])
    return {"rushing_yards": lambda: f("rushing", "YDS"), "receiving_yards": lambda: f("receiving", "YDS"),
            "passing_yards": lambda: f("passing", "YDS"), "receptions": lambda: f("receiving", "REC"),
            "rush_rec_yards": lambda: f("rushing", "YDS") + f("receiving", "YDS"),
            "passing_tds": lambda: f("passing", "TD"),
            "anytime_td": lambda: f("rushing", "TD") + f("receiving", "TD")}[mk]()


def main():
    d = pd.concat([pd.read_csv(f) for f in sorted(D.glob("*.csv"))], ignore_index=True)
    d = d.sort_values("snapshot_utc").drop_duplicates(["game", "market", "bet"], keep="last")
    g = data.load_games()
    out = []
    for game, h in d.groupby("game"):
        away, home = game.split("@")
        r = g[(g.away_team == away) & (g.home_team == home) & (g.season == data.current_season())]
        if r.empty or pd.isna(r.result.iloc[-1]):
            continue
        r = r.iloc[-1]
        ev = recs._events("nfl", r.gameday)
        for x in h.itertuples(index=False):
            bet = x.bet.split("  [ROLE")[0]
            if x.market == "alt spread":
                t, pt = bet.split(" ")
                margin = r.result if t == home else -r.result
                hit = margin + float(pt) > 0
            elif x.market == "alt total":
                side, pt = bet.split(" ")
                hit = (r.total > float(pt)) if side == "Over" else (r.total < float(pt))
            else:
                m = re.match(r"(.+?) (anytime TD|(\d+)\+ \w+)$", bet)
                s = recs._player_stats("nfl", ev, m.group(1))
                if s is None:
                    continue  # no box-score line: DK voids
                need = 1 if m.group(2) == "anytime TD" else float(m.group(3))
                hit = value(s, x.market) >= need
            out.append({**x._asdict(), "hit": bool(hit), "role_flag": "ROLE CHECK" in x.bet})
    r = pd.DataFrame(out)
    if r.empty:
        raise SystemExit("no finished games in picks/rungs_v2 yet")
    r["dec"] = np.where(r.price > 0, 1 + r.price / 100, 1 + 100 / -r.price)
    r["profit"] = np.where(r.hit, r.dec - 1, -1.0)
    r["edge"] = r.v2 - r.dk
    print(f"{len(r)} graded DK rungs, {r.game.nunique()} games\n")
    for lab, q in (("all", r), ("no ROLE CHECK", r[~r.role_flag])):
        b = pd.cut(q.edge, [-1, -0.03, 0.03, 0.06, 0.10, 1], labels=["v2 < DK", "about even", "+3-6%", "+6-10%", "+10%+"])
        t = q.groupby(b, observed=True).agg(n=("hit", "size"), v2=("v2", "mean"), dk=("dk", "mean"),
                                           hit=("hit", "mean"), profit_per_1=("profit", "mean"))
        print(f"{lab}:\n{t.round(3).to_string()}\n")
    print("by market (v2 3%+ over DK, no ROLE CHECK):")
    q = r[(r.edge >= 0.03) & ~r.role_flag]
    print(q.groupby("market").agg(n=("hit", "size"), v2=("v2", "mean"), dk=("dk", "mean"), hit=("hit", "mean"),
                                  profit_per_1=("profit", "mean")).round(3).to_string())
    print("\nRungs of one player move together, so the real sample is closer to player-games than rungs.")


if __name__ == "__main__":
    main()
