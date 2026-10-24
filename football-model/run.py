"""NFL betting model CLI.

  python run.py backtest              # walk-forward test, tuned 2015-2022, held-out 2023+
  python run.py card                  # this week's card: spreads vs opening line, game-day totals
  python run.py card --week 7 --line MIN=-5.5 --save
  python run.py grade                 # grade every saved card against final scores
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from nflmodel import data, model, pipeline

# Chosen on 2015-2022 only. Held out 2023-2026 at these cutoffs: spreads 54-38 (58.7%).
SPREAD_BET_P = 0.56
TOTAL_BET_P = 0.55
# Outdoor games at 15+ mph wind or with rain/snow went Under 55% in 2009-2022 and in 2023+;
# the only totals situation that held up in both periods. Everything else is a coin flip.
WEATHER_UNDER_WIND = 15
PICKS = data.ROOT / "picks"
HOLDOUT = 2023


def _rec(r):
    if not r["bets"]:
        return "no bets"
    return f"{r['wins']}-{r['bets'] - r['wins']} ({r['rate']:.1%}, ROI {r['roi']:+.1%} at -110)"


def cmd_backtest(args):
    df = pipeline.load(args.refresh, use_forecasts=False)
    seasons = range(2015, data.current_season() + 1)
    for name, make, target, cut in (("SPREADS vs opening line", model.spread_market, "result", SPREAD_BET_P),
                                    ("TOTALS vs closing total", model.total_market, "total", TOTAL_BET_P)):
        p = model.walk_forward(df, make, seasons)
        print(f"\n=== {name} ===")
        for th in sorted({0.53, 0.55, cut}):
            tune = model.record(p[p["season"] < HOLDOUT], target, th)
            hold = model.record(p[p["season"] >= HOLDOUT], target, th)
            mark = "  <- bet cutoff" if th == cut else ""
            print(f"  P >= {th:.2f}: 2015-{HOLDOUT - 1} {_rec(tune)} | {HOLDOUT}+ {_rec(hold)}{mark}")
        print("  calibration (predicted vs actual win rate of the favored side):")
        print(model.calibration(p, target).to_string())
    print("\nBreak-even at -110 is 52.4%.")


def _side(p, home, away, line, kind):
    """(bet label, P(bet wins)) for the side the model favors."""
    if kind == "spread":
        return (f"{home} {-line:+.1f}", p) if p >= 0.5 else (f"{away} {line:+.1f}", 1 - p)
    return (f"Over {line:g}", p) if p >= 0.5 else (f"Under {line:g}", 1 - p)


def cmd_card(args):
    df = pipeline.load(args.refresh)
    season = args.season or data.current_season()
    upcoming = df[(df["season"] == season) & df["result"].isna()]
    week = args.week or int(upcoming["week"].min())
    games = upcoming[upcoming["week"] == week]
    spread, total = model.spread_market().fit(df), model.total_market().fit(df)

    # Spread to judge: your book's number if given, else the opener, else the current line.
    line = games["spread_open"].fillna(games["spread_line"]).copy()
    for item in args.line or []:
        team, val = item.split("=")
        team = team.upper()
        line[games["home_team"] == team] = -float(val)
        line[games["away_team"] == team] = float(val)
    ps, pt = spread.predict(games, line), total.predict(games)

    # Last QB to start for each team; a listed starter who differs needs checking.
    played = df[df["result"].notna()].sort_values("gameday")
    last_qb = {}
    for g in played.itertuples(index=False):
        last_qb[g.home_team], last_qb[g.away_team] = g.home_qb, g.away_qb

    rows = []
    print(f"\n{season} week {week} card  (bet only rows marked BET; P = chance the bet wins)\n")
    for (_, g), (_, s), (_, t) in zip(games.iterrows(), ps.iterrows(), pt.iterrows()):
        print(f"{g.away_team} @ {g.home_team}  {g.gameday:%a %m/%d} {g.gametime} ET  ({g.away_qb} vs {g.home_qb})")
        qb_flags = [f"{t} lists {q} but {last_qb[t]} started last game" for t, q in
                    ((g.away_team, g.away_qb), (g.home_team, g.home_qb)) if t in last_qb and last_qb[t] != q]
        for f in qb_flags:
            print(f"   QB CHECK: {f}; the spread pick assumes {f.split(' lists ')[1].split(' but')[0]} plays")
        for kind, pr, cut in (("spread", s, SPREAD_BET_P), ("total", t, TOTAL_BET_P)):
            if np.isnan(pr.p):
                print(f"   {kind}: no line yet")
                continue
            label, prob = _side(pr.p, g.home_team, g.away_team, pr.line, kind)
            bet = prob >= cut and not (kind == "spread" and qb_flags)
            fair = (f"model {g.home_team} {-pr.rating:+.1f}" if kind == "spread"
                    else f"model total {pr.rating:.1f}")
            hold = "HOLD (QB check)" if prob >= cut and not bet else ""
            print(f"   {kind:6} {label:14} P {prob:.0%}  ({fair})  {'BET' if bet else hold}")
            if kind == "total" and not g.dome and (g.wind >= WEATHER_UNDER_WIND or g.rain or g.snow):
                why = f"wind {g.wind:.0f} mph" if g.wind >= WEATHER_UNDER_WIND else "rain/snow forecast"
                print(f"   WEATHER UNDER {pr.line:g}: {why} (such games went Under ~55%, 2009-2026)")
            rows.append({"season": season, "week": week, "game_id": g.game_id, "kind": kind,
                         "home_team": g.home_team, "away_team": g.away_team, "line": pr.line,
                         "pick": label, "p": round(prob, 3), "bet": bet, "qb_check": bool(qb_flags)})
    if args.save:
        PICKS.mkdir(exist_ok=True)
        path = PICKS / f"{season}_wk{week:02d}.csv"
        if path.exists() and not args.force:
            print(f"\n{path.name} already saved; a card is posted once (use --force to replace)")
        else:
            pd.DataFrame(rows).to_csv(path, index=False)
            print(f"\nsaved {path}")


def cmd_grade(args):
    games = data.load_games(args.refresh).set_index("game_id")
    files = sorted(PICKS.glob("*.csv"))
    if not files:
        print("no saved cards yet (run: python run.py card --save)")
        return
    log = pd.concat([pd.read_csv(f) for f in files])
    log = log[log["bet"]]
    out = []
    for r in log.itertuples(index=False):
        g = games.loc[r.game_id]
        if np.isnan(g.result):
            res = "pending"
        else:
            actual = g.result if r.kind == "spread" else g.total
            home_or_over = r.pick.startswith(r.home_team) if r.kind == "spread" else r.pick.startswith("Over")
            diff = (actual - r.line) * (1 if home_or_over else -1)
            res = "push" if diff == 0 else ("win" if diff > 0 else "loss")
        out.append({"week": r.week, "pick": r.pick, "p": r.p, "result": res})
    out = pd.DataFrame(out)
    print(out.to_string(index=False))
    w, l = (out["result"] == "win").sum(), (out["result"] == "loss").sum()
    if w + l:
        print(f"\nrecord {w}-{l}  ({w / (w + l):.1%}), units {w * 100 / 110 - l:+.2f} at -110")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="force re-download of data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backtest")
    c = sub.add_parser("card")
    c.add_argument("--season", type=int)
    c.add_argument("--week", type=int)
    c.add_argument("--line", action="append", help="your book's spread for a team, e.g. MIN=-5.5")
    c.add_argument("--save", action="store_true", help="save the card to picks/ for grading")
    c.add_argument("--force", action="store_true", help="replace an already-saved card")
    sub.add_parser("grade")
    args = ap.parse_args()
    {"backtest": cmd_backtest, "card": cmd_card, "grade": cmd_grade}[args.cmd](args)


if __name__ == "__main__":
    main()
