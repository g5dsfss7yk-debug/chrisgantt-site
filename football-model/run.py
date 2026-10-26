"""NFL betting model CLI.

  python run.py backtest              # walk-forward test, tuned 2015-2022, held-out 2023+
  python run.py card                  # this week's card: spreads vs opening line, weather totals
  python run.py card --week 7 --line MIN=-5.5 --save
  python run.py grade                 # grade every saved card against final scores
  python run.py props --team SF --odds "George Kittle=+120"   # anytime TD chances
  python run.py lineup --team DAL     # starters at every position and missing regulars
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from nflmodel import data, lineups, model, pipeline, props

# Spread tiers need all three models on the same side of the line. Held out 2023-2026:
# STRONG (P >= 55%) 69-54 (56.1%), LEAN (P >= 53%) 177-131 (57.5%); 2015-2022: 62.6% / 57.9%.
TIERS = (("STRONG", 0.55), ("LEAN", 0.53))
# Model totals lost in 2023-2026 with every learner, so totals come only from situations
# that held up in both periods: outdoor wind 15+ mph or rain/snow went Under ~55%.
WEATHER_UNDER_WIND = 15
# Games in the top 10% of defensive injury burden went Over 64% in 2023+ (flat before): watch only.
DEF_INJURY_WATCH = 1.98
PICKS = data.ROOT / "picks"
# Anytime-TD odds carry a large hold, so only flag a prop when the model clears the book's
# implied chance by this much.
PROP_EDGE = 0.05
HOLDOUT = 2023


def _rec(r):
    if not r["bets"]:
        return "no bets"
    return f"{r['wins']}-{r['bets'] - r['wins']} ({r['rate']:.1%}, ROI {r['roi']:+.1%} at -110)"


def cmd_backtest(args):
    df = pipeline.load(args.refresh, use_forecasts=False)
    seasons = range(2015, data.current_season() + 1)
    for name, make, target in (("SPREADS vs opening line", model.spread_market, "result"),
                               ("TOTALS vs closing total", model.total_market, "total")):
        p = model.walk_forward(df, make, seasons)
        print(f"\n=== {name}: ensemble of {', '.join(model.LEARNERS)} ===")
        for tier, th in TIERS:
            agreed = p[p["agree"] == p["n_models"]]
            tune = model.record(agreed[agreed["season"] < HOLDOUT], target, th)
            hold = model.record(agreed[agreed["season"] >= HOLDOUT], target, th)
            print(f"  {tier:6} P >= {th:.2f}, all agree: 2015-{HOLDOUT - 1} {_rec(tune)} | {HOLDOUT}+ {_rec(hold)}")
        print("  calibration (predicted vs actual win rate of the favored side):")
        print(model.calibration(p, target).to_string())
    print("\nBreak-even at -110 is 52.4%. Totals are not bet from the model (see TIERS note).")


def _tier(prob, agree, n):
    if agree < n:
        return ""
    return next((name for name, cut in TIERS if prob >= cut), "")


def _side(p, home, away, line, kind):
    """(bet label, P(bet wins)) for the side the model favors."""
    if kind == "spread":
        return (f"{home} {-line:+.1f}", p) if p >= 0.5 else (f"{away} {line:+.1f}", 1 - p)
    return (f"Over {line:g}", p) if p >= 0.5 else (f"Under {line:g}", 1 - p)


def cmd_card(args):
    qbs = dict(q.split("=", 1) for q in args.qb or [])
    qbs = {t.upper(): n for t, n in qbs.items()}
    season = args.season or data.current_season()
    df = pipeline.load(args.refresh, qbs=qbs, season=season, week=args.week)
    if qbs and not args.week:
        raise SystemExit("--qb needs --week")
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
    print(f"\n{season} week {week} card  (bet rows marked STRONG / LEAN / WEATHER; P = chance the bet wins;"
          f" models = how many of {len(model.LEARNERS)} agree)\n")
    for (_, g), (_, s), (_, t) in zip(games.iterrows(), ps.iterrows(), pt.iterrows()):
        print(f"{g.away_team} @ {g.home_team}  {g.gameday:%a %m/%d} {g.gametime} ET  ({g.away_qb} vs {g.home_qb})")
        qb_flags = [f"{t} lists {q} but {last_qb[t]} started last game" for t, q in
                    ((g.away_team, g.away_qb), (g.home_team, g.home_qb))
                    if t in last_qb and last_qb[t] != q and t not in qbs]  # --qb confirms it
        for f in qb_flags:
            print(f"   QB CHECK: {f}; the spread pick assumes {f.split(' lists ')[1].split(' but')[0]} plays")
        picks = []
        if not np.isnan(s.p):
            label, prob = _side(s.p, g.home_team, g.away_team, s.line, "spread")
            tier = _tier(prob, s.agree, s.n_models)
            if tier and qb_flags:
                tier = "HOLD (QB check)"
            each = "  ".join(f"{n} {g.home_team} {-s[f'rating_{n}']:+.1f}" for n in model.LEARNERS)
            print(f"   spread {label:14} P {prob:.0%}  models {int(s.agree)}/{int(s.n_models)}  ({each})  {tier}")
            picks.append(("spread", s.line, label, prob, tier))
        else:
            print("   spread: no line yet")
        if not np.isnan(t.line):
            print(f"   total  {t.line:g}: model {t.rating:.1f} (info only; model totals are not bet)")
            if not g.dome and (g.wind >= WEATHER_UNDER_WIND or g.rain or g.snow):
                why = f"wind {g.wind:.0f} mph" if g.wind >= WEATHER_UNDER_WIND else "rain/snow forecast"
                print(f"   total  Under {t.line:g}  {why}: such games went Under ~55% (2009-2026)  WEATHER")
                picks.append(("total", t.line, f"Under {t.line:g}", 0.55, "WEATHER"))
            elif g.inj_def_sum >= DEF_INJURY_WATCH:
                print(f"   total  Over {t.line:g}  heavy defensive injuries: watch only, not a bet")
        for kind, ln, label, prob, tier in picks:
            rows.append({"season": season, "week": week, "game_id": g.game_id, "kind": kind,
                         "home_team": g.home_team, "away_team": g.away_team, "line": ln, "pick": label,
                         "p": round(prob, 3), "tier": tier,
                         "bet": tier in ("STRONG", "LEAN", "WEATHER"), "qb_check": bool(qb_flags)})
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
        tier = r.tier if isinstance(getattr(r, "tier", None), str) else "STRONG"  # pre-tier cards
        out.append({"week": r.week, "pick": r.pick, "p": r.p, "tier": tier, "result": res})
    out = pd.DataFrame(out)
    print(out.to_string(index=False))
    for name, part in [("all", out)] + list(out.groupby("tier")):
        w, l = (part["result"] == "win").sum(), (part["result"] == "loss").sum()
        if w + l:
            print(f"{name:8} {w}-{l}  ({w / (w + l):.1%}), units {w * 100 / 110 - l:+.2f} at -110")


def _american(odds: str) -> float:
    """Implied probability of American odds (+150 -> 0.40, -120 -> 0.545)."""
    o = float(odds)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def cmd_props(args):
    games = data.load_games(args.refresh)
    season = args.season or data.current_season()
    upcoming = games[(games["season"] == season) & games["result"].isna()]
    week = args.week or int(upcoming["week"].min())
    for gid, f in pipeline.forecasts().items():  # game-day wind for the props weather input
        games.loc[games["game_id"] == gid, "wind"] = f["wind"]
    pg = props.load_player_games(args.refresh)
    up = props.upcoming(pg, games, season, week, data.load_injuries([season], args.refresh),
                        lineups.load_depth(season, args.refresh))
    d = props.build(pd.concat([pg, up], ignore_index=True), games)
    models = props.fit(d[d["td"].notna()])
    today = d[d["td"].isna()].copy()
    today["p"] = props.predict(models, today)
    if args.team:
        today = today[today["team"].isin([t.upper() for t in args.team])]
    odds = {}
    for item in args.odds or []:
        name, o = item.rsplit("=", 1)
        odds[name.strip().lower()] = o
    print(f"\n{season} week {week} anytime TD  (P = model chance of a rushing or receiving TD;"
          f" out/doubtful players removed)\n")
    for (gid, team), grp in today.sort_values("p", ascending=False).groupby(["game_id", "team"], sort=False):
        grp = grp[grp["p"] >= args.min_p]
        if grp.empty:
            continue
        print(f"{team} vs {grp['opponent_team'].iloc[0]}  (team implied {grp['implied_pts'].iloc[0]:.1f} pts)")
        for r in grp.itertuples(index=False):
            fair = (100 / r.p - 100) if r.p < 0.5 else -(100 * r.p / (1 - r.p))
            line = f"   {r.player_display_name:24} {r.position:2}  P {r.p:.0%}  fair odds {fair:+.0f}"
            book = odds.get(r.player_display_name.lower())
            if book:
                edge = r.p - _american(book)
                line += f"  | book {book} ({_american(book):.0%})  edge {edge:+.0%}  {'VALUE' if edge >= PROP_EDGE else ''}"
            print(line)
    print(f"\nProbabilities are calibrated (2016-2026 walk-forward), but there is no free archive of prop odds,"
          f" so profit against books is untested. VALUE = model beats the book's implied chance by {PROP_EDGE:.0%}+.")


def cmd_lineup(args):
    games = data.load_games(args.refresh)
    season = args.season or data.current_season()
    upcoming = games[(games["season"] == season) & games["result"].isna()]
    week = args.week or int(upcoming["week"].min())
    wk = upcoming[upcoming["week"] == week]
    if args.team:
        t = [x.upper() for x in args.team]
        wk = wk[wk["home_team"].isin(t) | wk["away_team"].isin(t)]
    for g in wk.itertuples(index=False):
        print(f"\n=== {g.away_team} @ {g.home_team}  {pd.Timestamp(g.gameday):%a %m/%d} {g.gametime} ET ===")
        for team in (g.away_team, g.home_team):
            r = lineups.report(team, season, week, args.refresh)
            st = r["starters"]
            print(f"\n{team} starters (depth chart; * = Out/Doubtful on the injury report)")
            for grp in ("offense", "defense"):
                rows = st[st["pos_grp"].str.contains("D$|Defense|3-4|4-3|Nickel", regex=True, na=False)] if grp == "defense" \
                    else st[~st["pos_grp"].str.contains("D$|Defense|3-4|4-3|Nickel|Special", regex=True, na=False)]
                print(f"  {grp:8} " + ", ".join(f"{p.pos_abb} {p.player_name}{'*' if p.out else ''}" for p in rows.itertuples()
                                           if isinstance(p.player_name, str)))
            m = r["missing"]
            if len(m):
                print("  missing regulars (share of snaps, last 2 games): " +
                      "; ".join(f"{x.position} {x.player} {x.pct:.0%} ({x.status})" for x in m.itertuples()))
            else:
                print("  missing regulars: none")
            if r["questionable"]:
                print("  questionable: " + ", ".join(r["questionable"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="force re-download of data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backtest")
    c = sub.add_parser("card")
    c.add_argument("--season", type=int)
    c.add_argument("--week", type=int)
    c.add_argument("--line", action="append", help="your book's spread for a team, e.g. MIN=-5.5")
    c.add_argument("--qb", action="append", help='confirmed starter, e.g. PHI="Tanner McKee" (needs --week)')
    c.add_argument("--save", action="store_true", help="save the card to picks/ for grading")
    c.add_argument("--force", action="store_true", help="replace an already-saved card")
    sub.add_parser("grade")
    pr = sub.add_parser("props")
    pr.add_argument("--season", type=int)
    pr.add_argument("--week", type=int)
    pr.add_argument("--team", action="append", help="only these teams, e.g. --team SF --team ATL")
    pr.add_argument("--odds", action="append", help='your book\'s anytime TD odds, e.g. "George Kittle=+120"')
    pr.add_argument("--min-p", type=float, default=0.15, help="hide players below this chance")
    ln = sub.add_parser("lineup")
    ln.add_argument("--season", type=int)
    ln.add_argument("--week", type=int)
    ln.add_argument("--team", action="append")
    args = ap.parse_args()
    {"backtest": cmd_backtest, "card": cmd_card, "grade": cmd_grade, "props": cmd_props,
     "lineup": cmd_lineup}[args.cmd](args)


if __name__ == "__main__":
    main()
