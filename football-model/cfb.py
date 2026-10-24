"""College football betting model CLI.

  python cfb.py backtest                        # walk-forward test, tuned 2017-2021, held out 2022+
  python cfb.py card                            # next game day: fair spread for every FBS game
  python cfb.py card --line "Iowa=-7.5" --total "Iowa=40.5" --save
  python cfb.py grade                           # grade saved cards against final scores
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from cfbmodel import data, markets, pipeline
from nflmodel import model

# Against opening lines, all three models agreeing at P >= 55% went 219-166 (56.9%) in
# 2017-2021 and 54-40 (57.4%) in 2022-2025. Against closing lines there is no edge.
# Model totals are not bet. Re-tested with the stage-2 Under lean removed and the gap
# centered on recent games: vs the opening total, P >= 55% went 198-172 (53.5%) in
# 2017-2021 and 34-35 (49.3%) in 2022-2025, and the most confident picks did worst.
STRONG = 0.55
# Closing totals of 65+ went Under 55.3% in 2016-2021 and 56.2% in 2022-2025, but only
# 51.6% (n=31) and 41.7% (n=24) in 2024-2025, so this is a watch flag, not a bet.
HIGH_TOTAL_UNDER = 65
HOLDOUT = 2022
PICKS = data.ROOT / "picks" / "cfb"


def _rec(r):
    if not r["bets"]:
        return "no bets"
    return f"{r['wins']}-{r['bets'] - r['wins']} ({r['rate']:.1%}, ROI {r['roi']:+.1%} at -110)"


def cmd_backtest(args):
    df = pipeline.load(args.refresh)
    seasons = range(2017, data.current_season())
    for name, make, target in (("SPREADS vs opening line", markets.spread_market, "result"),
                               ("SPREADS vs closing line", lambda: markets.spread_market("spread_close"), "result"),
                               ("TOTALS vs opening total", markets.total_market, "total"),
                               ("TOTALS vs closing total", lambda: markets.total_market("total_line"), "total")):
        p = model.walk_forward(df, make, seasons)
        agreed = p[p["agree"] == p["n_models"]]
        tune = model.record(agreed[agreed["season"] < HOLDOUT], target, STRONG)
        hold = model.record(agreed[agreed["season"] >= HOLDOUT], target, STRONG)
        print(f"\n=== {name} ===\n  P >= {STRONG:.2f}, all agree: 2017-{HOLDOUT - 1} {_rec(tune)} | {HOLDOUT}+ {_rec(hold)}")
        print(model.calibration(p, target).to_string())


def _find(games, name):
    name = name.lower()
    for col in ("home_team", "away_team"):
        hit = games[games[col].str.lower() == name]
        if len(hit) == 1:
            return hit.index[0], col
    hits = [(i, c) for c in ("home_team", "away_team") for i in games.index[games[c].str.lower().str.contains(name, regex=False)]]
    if len(hits) != 1:
        raise SystemExit(f"--line team '{name}' matched {len(hits)} games; use the full school name")
    return hits[0]


def cmd_card(args):
    df = pipeline.load(args.refresh)
    upcoming = df[df["result"].isna()]
    day = pd.Timestamp(args.date) if args.date else upcoming["gameday"].min()
    games = upcoming[upcoming["gameday"] == day].sort_values("kickoff_et")
    spread = markets.spread_market().fit(df)
    total = markets.total_market().fit(df)

    line = games["spread_open"].copy()  # empty until the season's lines are published
    for item in args.line or []:
        team, val = item.rsplit("=", 1)
        i, col = _find(games, team.strip())
        line[i] = -float(val) if col == "home_team" else float(val)
    ps = spread.predict(games, line)
    tline = games["total_open"].copy()
    for item in args.total or []:
        team, val = item.rsplit("=", 1)
        i, _ = _find(games, team.strip())
        tline[i] = float(val)
    pt = total.predict(games, tline)

    print(f"\nCFB card {day:%a %m/%d/%Y}  (fair = model's line for the home team; P = chance the bet wins vs the line"
          f" you gave; models = how many of {len(model.LEARNERS)} agree)\n")
    rows = []
    for (_, g), (_, s), (_, t) in zip(games.iterrows(), ps.iterrows(), pt.iterrows()):
        fair = -s.rating
        each = " ".join(f"{-s[f'rating_{n}']:+.1f}" for n in model.LEARNERS)
        flags = [f"{side.upper()} QB changed last game ({g[f'{side}_qb']})" for side in ("home", "away") if g[f"{side}_qb_change"]]
        head = f"{g.kickoff_et:%I:%M%p} {g.away_team} @ {g.home_team}{' (neutral)' if g.neutral else ''}"
        print(f"{head:58} fair {g.home_team} {fair:+.1f}  ({each})  total {t.rating:.0f}")
        for f in flags:
            print(f"   QB CHECK: {f}")
        if not np.isnan(t.p):
            tlabel, tprob = (f"Over {t.line:g}", t.p) if t.p >= 0.5 else (f"Under {t.line:g}", 1 - t.p)
            ttier = ""
            print(f"   total:   {tlabel:30} P {tprob:.0%}  models {int(t.agree)}/{int(t.n_models)}  (info only, not bet)")
            if t.line >= HIGH_TOTAL_UNDER:
                print(f"   total:   Under {t.line:g}  total of {HIGH_TOTAL_UNDER}+: watch only (faded in 2024-2025)")
            rows.append({"season": g.season, "gameday": f"{day:%Y-%m-%d}", "game_id": g.game_id, "kind": "total",
                         "home_team": g.home_team, "away_team": g.away_team, "line": t.line, "pick": tlabel,
                         "p": round(tprob, 3), "tier": ttier, "bet": ttier == "STRONG"})
        if np.isnan(s.p):
            continue
        if s.p >= 0.5:
            label, prob = f"{g.home_team} {-s.line:+.1f}", s.p
        else:
            label, prob = f"{g.away_team} {s.line:+.1f}", 1 - s.p
        tier = "STRONG" if prob >= STRONG and s.agree == s.n_models and not flags else ""
        print(f"   vs line: {label:30} P {prob:.0%}  models {int(s.agree)}/{int(s.n_models)}  {tier}")
        rows.append({"season": g.season, "gameday": f"{day:%Y-%m-%d}", "game_id": g.game_id, "kind": "spread",
                     "home_team": g.home_team, "away_team": g.away_team, "line": s.line, "pick": label,
                     "p": round(prob, 3), "tier": tier, "bet": tier == "STRONG"})
    print("\nThe edge held up only against OPENING lines. Against a line that has already moved, "
          "treat P as an upper bound.")
    if args.save and rows:
        PICKS.mkdir(parents=True, exist_ok=True)
        path = PICKS / f"{day:%Y-%m-%d}.csv"
        if path.exists() and not args.force:
            print(f"{path.name} already saved; a card is posted once (use --force to replace)")
        else:
            pd.DataFrame(rows).to_csv(path, index=False)
            print(f"saved {path}")


def cmd_grade(args):
    games = data.load_schedules(args.refresh).set_index("game_id")
    files = sorted(PICKS.glob("*.csv"))
    if not files:
        print("no saved CFB cards yet (run: python cfb.py card --line ... --save)")
        return
    log = pd.concat([pd.read_csv(f) for f in files])
    log = log[log["bet"]]
    out = []
    for r in log.itertuples(index=False):
        g = games.loc[r.game_id]
        if np.isnan(g.result):
            res = "pending"
        else:
            kind = getattr(r, "kind", "spread")
            if kind == "total":
                diff = (g.total - r.line) * (1 if r.pick.startswith("Over") else -1)
            else:
                diff = (g.result - r.line) * (1 if r.pick.startswith(r.home_team + " ") else -1)
            res = "push" if diff == 0 else ("win" if diff > 0 else "loss")
        out.append({"day": r.gameday, "pick": r.pick, "p": r.p, "result": res})
    out = pd.DataFrame(out)
    print(out.to_string(index=False))
    w, l = (out["result"] == "win").sum(), (out["result"] == "loss").sum()
    if w + l:
        print(f"record {w}-{l} ({w / (w + l):.1%}), units {w * 100 / 110 - l:+.2f} at -110")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="force re-download of data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backtest")
    c = sub.add_parser("card")
    c.add_argument("--date", help="game day, YYYY-MM-DD (default: next day with games)")
    c.add_argument("--line", action="append", help='your book\'s spread for a team, e.g. "Iowa=-7.5"')
    c.add_argument("--total", action="append", help='your book\'s total for a game, by either team, e.g. "Iowa=40.5"')
    c.add_argument("--save", action="store_true")
    c.add_argument("--force", action="store_true")
    sub.add_parser("grade")
    args = ap.parse_args()
    {"backtest": cmd_backtest, "card": cmd_card, "grade": cmd_grade}[args.cmd](args)


if __name__ == "__main__":
    main()
