"""NFL game model CLI.

  python run.py picks                       # early-week spread picks vs the opening line
  python run.py backtest                    # walk-forward test 2015-2025 vs Vegas
  python run.py predict                     # upcoming unplayed games this week
  python run.py predict --week 7 --weather BUF=28,18,gust=30,snow --weather 2026_07_GB_DET=30,5
      forecast override: TEAM or GAME_ID = tempF,windMPH[,gust=MPH][,rain|snow|rain=0.5]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from nflmodel import data, features, model, teams


def load(refresh=False, weather=None):
    games = data.load_games(refresh)
    seasons = range(model.FIRST_TRAIN_SEASON, data.current_season() + 1)
    inj = data.load_injuries(seasons, refresh)
    snaps = data.load_snaps(seasons, refresh)
    pbp = data.load_team_pbp(range(model.FIRST_TRAIN_SEASON - 1, data.current_season() + 1), refresh)
    rosters = data.load_rosters(seasons, refresh)
    cont = features.roster_continuity(snaps, rosters)
    wx = data.load_game_weather(seasons, refresh)
    nfelo = data.load_nfelo(refresh)
    return features.build(games, features.injury_scores(inj, snaps), weather, pbp, cont, wx, nfelo)


def _pct(w, l):
    return f"{w}-{l} ({w / max(w + l, 1):.1%})"


def cmd_backtest(args):
    df = load(args.refresh)
    seasons = range(2015, data.current_season())
    for wm in (False, True):
        r = model.backtest(df, seasons, with_market=wm)
        label = ("MODEL + VEGAS LINES AS INPUT" if wm
                 else "DEFAULT (spread: model alone; total: anchored to the Vegas total)")
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


def forecast_overrides() -> dict:
    """Weather job forecasts -> per-game overrides (rain/snow as 0, 0.5 or 1)."""
    fc = data.load_forecasts()
    out = {}
    for f in fc.itertuples(index=False):
        p = f.precip_prob if pd.notna(f.precip_prob) else 0
        wet = 1.0 if p >= 60 and f.precip_in >= 0.05 else (0.5 if p >= 35 else 0.0)
        snowy = f.snow_in >= 0.1
        out[f.game_id] = {"temp": f.temp, "wind": f.wind, "gust": f.gust,
                          "rain": 0.0 if snowy else wet, "snow": max(wet, 0.5) if snowy else 0.0}
    if out:
        print(f"using forecasts for {len(out)} outdoor games (fetched {fc['fetched_at'].max()})")
    return out


def cmd_predict(args):
    weather = {} if args.no_forecast else forecast_overrides()
    for w in args.weather or []:
        key, vals = w.split("=", 1)
        t, wd, *extra = vals.split(",")
        ov = {"temp": float(t), "wind": float(wd)}
        for e in extra:
            name, _, val = e.partition("=")
            ov[name] = float(val) if val else 1.0
        weather[key] = ov
    df = load(args.refresh, weather)
    season = args.season or data.current_season()
    upcoming = df[(df["season"] == season) & df["result"].isna()]
    week = args.week or int(upcoming["week"].min())
    target = upcoming[upcoming["week"] == week]
    train = df[(df["season"] >= model.FIRST_TRAIN_SEASON) & df["result"].notna()]
    m = model.Model().fit(train)
    p = m.predict(target)

    print(f"\n{season} week {week} — spread: model alone; total: anchored to the Vegas total\n")
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
        wtxt = "dome" if f.dome else (f"{f.temp:.0f}F, wind {f.wind:.0f} (gust {f.gusty + 20:.0f})" if f.gusty
                                      else f"{f.temp:.0f}F, wind {f.wind:.0f} mph")
        wtxt += " rain" * bool(f.rain) + " snow" * bool(f.snow)
        print(f"   weather: {wtxt}   "
              f"injury burden off/def: {g.away_team} {a_off:.1f}/{a_def:.1f}, "
              f"{g.home_team} {h_off:.1f}/{h_def:.1f}")
        rows.append({**g.to_dict(), "spread_edge": edge, "total_edge": tedge})
    out = data.ROOT / "reports" / f"predictions_{season}_wk{week}.csv"
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nsaved {out}")


PICK_EDGE = 3.0


def cmd_picks(args):
    """Spread picks from the early-week model, graded against the opening line.

    The edge is against openers: lines move toward the model ~64% of the time, so bet
    as early as possible. --line TEAM=SPREAD checks the number your book offers now.
    """
    df = load(args.refresh)
    nf = data.load_nfelo(args.refresh)
    opens = {(x.season, x.week, x.home_fr, x.away_fr): -x.home_line_open for x in nf.itertuples(index=False)}
    season = args.season or data.current_season()
    upcoming = df[(df["season"] == season) & df["result"].isna()]
    week = args.week or int(upcoming["week"].min())
    target = upcoming[upcoming["week"] == week]
    train = df[(df["season"] >= model.FIRST_TRAIN_SEASON) & df["result"].notna()]
    m = model.Model(early=True).fit(train)
    p = m.predict(target)
    mine = {}
    for item in args.line or []:
        team, val = item.split("=")
        mine[team.upper()] = float(val)

    print(f"\n{season} week {week} spread picks (early-week model; bet edges >= {PICK_EDGE:g} pts)\n")
    print(f"{'game':14}{'model':>12}{'open':>8}{'now':>8}   pick")
    for g in p.itertuples(index=False):
        key = (g.season, g.week, teams.franchise(g.home_team), teams.franchise(g.away_team))
        opened = opens.get(key, np.nan)
        line = g.spread_line
        for team, sign in ((g.home_team, -1), (g.away_team, 1)):
            if team in mine:  # book spread quoted for that team, e.g. NE=-7.5
                line = sign * mine[team]
        ref = opened if np.isnan(line) else line
        edge = g.pred_margin - ref
        side, num = (g.home_team, -ref) if edge > 0 else (g.away_team, ref)
        pick = f"{side} {num:+.1f}  (edge {abs(edge):.1f})" if abs(edge) >= PICK_EDGE else "-"
        fmt = lambda v: "-" if np.isnan(v) else f"{v:+.1f}"
        print(f"{g.away_team + ' @ ' + g.home_team:14}{g.pred_margin:>+12.1f}{fmt(opened):>8}{fmt(g.spread_line):>8}   {pick}")
    print("\nmodel/open/now = expected home margin (+ = home favored). Picks use --line if given, "
          "else the current line.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="force re-download of data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backtest")
    pk = sub.add_parser("picks")
    pk.add_argument("--season", type=int)
    pk.add_argument("--week", type=int)
    pk.add_argument("--line", action="append", help="your book's spread, e.g. NE=-7.5")
    pp = sub.add_parser("predict")
    pp.add_argument("--season", type=int)
    pp.add_argument("--week", type=int)
    pp.add_argument("--no-forecast", action="store_true", help="ignore the weather job's forecasts")
    pp.add_argument("--weather", action="append",
                    help="override forecast: TEAM=tempF,windMPH[,gust=MPH][,rain|snow]")
    args = ap.parse_args()
    {"backtest": cmd_backtest, "predict": cmd_predict, "picks": cmd_picks}[args.cmd](args)


if __name__ == "__main__":
    main()
