"""NFL game model CLI.

  python run.py backtest                    # walk-forward test 2015-2025 vs Vegas
  python run.py predict                     # upcoming unplayed games this week
  python run.py predict --week 7 --weather BUF=28,18 --weather 2026_07_GB_DET=30,5
"""
from __future__ import annotations

import argparse

import pandas as pd

from nflmodel import data, features, model


def load(refresh=False, weather=None):
    games = data.load_games(refresh)
    seasons = range(model.FIRST_TRAIN_SEASON, data.current_season() + 1)
    inj = data.load_injuries(seasons, refresh)
    snaps = data.load_snaps(seasons, refresh)
    return features.build(games, features.injury_scores(inj, snaps), weather)


def _pct(w, l):
    return f"{w}-{l} ({w / max(w + l, 1):.1%})"


def cmd_backtest(args):
    df = load(args.refresh)
    seasons = range(2015, data.current_season())
    for wm in (False, True):
        r = model.backtest(df, seasons, with_market=wm)
        label = "MODEL + VEGAS LINE AS INPUT" if wm else "MODEL ALONE (no betting lines used)"
        print(f"\n=== {label}: {r['games']} games, {seasons.start}-{seasons.stop - 1} ===")
        print(f"{'':22}{'model':>10}{'vegas':>10}")
        for k, lab in [("win_acc", "straight-up accuracy"), ("log_loss", "win log loss"),
                       ("brier", "win Brier"), ("margin_mae", "margin error (pts)"),
                       ("total_mae", "total error (pts)")]:
            print(f"{lab:22}{r[k]:>10.3f}{r['vegas_' + k]:>10.3f}")
        print("against the spread (model vs line, by min disagreement in pts):")
        for e, (w, l) in r["ats"].items():
            print(f"   edge >= {e:<4} {_pct(w, l)}")
        print("over/under:")
        for e, (w, l) in r["ou"].items():
            print(f"   edge >= {e:<4} {_pct(w, l)}")
        print("straight-up accuracy by season:", r["by_season"])
    print("\nBreak-even against the spread at -110 is 52.4%.")


def _fmt_spread(team, margin):
    return f"{team} {-abs(margin):+.1f}" if abs(margin) >= 0.25 else "pick'em"


def cmd_predict(args):
    weather = {}
    for w in args.weather or []:
        key, vals = w.split("=")
        t, wd = vals.split(",")
        weather[key] = (float(t), float(wd))
    df = load(args.refresh, weather)
    season = args.season or data.current_season()
    upcoming = df[(df["season"] == season) & df["result"].isna()]
    week = args.week or int(upcoming["week"].min())
    target = upcoming[upcoming["week"] == week]
    train = df[(df["season"] >= model.FIRST_TRAIN_SEASON) & df["result"].notna()]
    m = model.Model().fit(train)
    p = m.predict(target)

    print(f"\n{season} week {week} — model alone (no betting lines used as input)\n")
    rows = []
    for (_, g), (_, f) in zip(p.iterrows(), target.iterrows()):
        fav = g.home_team if g.pred_margin > 0 else g.away_team
        vfav = g.home_team if g.spread_line > 0 else g.away_team
        edge = g.pred_margin - g.spread_line if pd.notna(g.spread_line) else float("nan")
        tedge = g.pred_total - g.total_line if pd.notna(g.total_line) else float("nan")
        print(f"{g.away_team} @ {g.home_team}  {g.gameday:%a %m/%d} {g.gametime} ET   "
              f"({g.away_qb} vs {g.home_qb})")
        print(f"   model: {_fmt_spread(fav, g.pred_margin)}, {g.home_team} win {g.home_win_prob:.0%}, "
              f"total {g.pred_total:.1f}")
        if pd.notna(g.spread_line):
            print(f"   vegas: {_fmt_spread(vfav, g.spread_line)}, total {g.total_line}   "
                  f"-> spread lean: {g.home_team if edge > 0 else g.away_team} ({abs(edge):.1f} pts), "
                  f"total lean: {'Over' if tedge > 0 else 'Under'} ({abs(tedge):.1f} pts)")
        print("   drivers: " + ", ".join(f"{n} {v:+.1f}" for n, v in m.drivers(f)))
        h_off, h_def = (f.inj_off_sum + f.inj_off_diff) / 2, (f.inj_def_sum + f.inj_def_diff) / 2
        a_off, a_def = f.inj_off_sum - h_off, f.inj_def_sum - h_def
        print(f"   weather: {'dome' if f.dome else f'{f.temp:.0f}F, wind {f.wind:.0f} mph'}   "
              f"injury burden off/def: {g.away_team} {a_off:.1f}/{a_def:.1f}, "
              f"{g.home_team} {h_off:.1f}/{h_def:.1f}")
        rows.append({**g.to_dict(), "spread_edge": edge, "total_edge": tedge})
    out = data.ROOT / "reports" / f"predictions_{season}_wk{week}.csv"
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nsaved {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="force re-download of data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backtest")
    pp = sub.add_parser("predict")
    pp.add_argument("--season", type=int)
    pp.add_argument("--week", type=int)
    pp.add_argument("--weather", action="append",
                    help="override forecast: TEAM=tempF,windMPH or GAME_ID=tempF,windMPH")
    args = ap.parse_args()
    {"backtest": cmd_backtest, "predict": cmd_predict}[args.cmd](args)


if __name__ == "__main__":
    main()
