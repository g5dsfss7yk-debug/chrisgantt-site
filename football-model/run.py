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

from nflmodel import data, lineups, model, pipeline, props, statprops
import checks

# Spread tiers need all three models on the same side of the line. Held out 2023-2026:
# STRONG (P >= 55%) 69-54 (56.1%), LEAN (P >= 53%) 177-131 (57.5%); 2015-2022: 62.6% / 57.9%.
TIERS = (("STRONG", 0.55), ("LEAN", 0.53))
# Model totals have no tested edge (about 50% in every period), so they are leans only. The
# side comes from the re-leveled rating (see model.Market), not the raw one: the raw rating
# sits about a point below recent scoring and made the card lean Under in most games.
# Weather Unders (outdoor wind 15+ mph or rain/snow) went 53-67% in 2009-2023 but 49-52% in
# 2024-2026 as books caught up, so they are shown as a note, not a bet.
WEATHER_UNDER_WIND = 15
# Games in the top 10% of defensive injury burden went Over 64% in 2023+ (flat before): watch only.
DEF_INJURY_WATCH = 1.98
PICKS = data.ROOT / "picks"
# Anytime-TD odds carry a large hold, so only flag a prop when the model clears the book's
# implied chance by this much.
PROP_EDGE = 0.05
OU_VALUE = 0.574   # -110 breaks even at 52.4%; same 5-point cushion as the TD props
HOLDOUT = 2023
# 6-point teaser legs on underdogs of +1 to +2.5 (teased through 3 and 7) won 76.1% in 2009-2022
# and 78.8% in 2023-2026 (n=217) at the closing line; every other range was 65-73% since 2023
# (favorites -7.5 to -8.5 dropped from 76% to 65%). A 2-team 6-point teaser at -120 needs 73.9%
# per leg, at -130 75.2%, at -140 76.4%.
TEASER_DOG = (1.0, 2.5)
TEASER_PTS = 6


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


def _qb_overrides(args) -> dict:
    """--qb TEAM="Name" flags as {"TEAM": "Name"}."""
    return {t.strip().upper(): n.strip().strip('"') for t, n in (q.split("=", 1) for q in args.qb or [])}


def _auto_qbs(season: int, week: int | None, given: dict) -> dict:
    """Starters to use when the schedule's listed QB is stale: if the listed QB differs from
    both the depth chart's QB1 and the team's last starter, and those two agree, use them.
    (The schedule file can carry an old matchup's QB, e.g. a backup from weeks earlier.)"""
    g = data.load_games()
    up = g[(g["season"] == season) & g["result"].isna()]
    week = week or int(up["week"].min())
    up = up[up["week"] == week]
    played = g[g["result"].notna()].sort_values("gameday")
    last = {}
    for x in played.itertuples(index=False):
        last[x.home_team], last[x.away_team] = x.home_qb_name, x.away_qb_name
    depth = lineups.load_depth(season)
    qb1 = depth[depth["pos_abb"] == "QB"].sort_values("pos_rank").drop_duplicates("team").set_index("team")["player_name"]
    norm = lambda n: lineups._norm(pd.Series([str(n)]))[0]
    out = {}
    for x in up.itertuples(index=False):
        for team, listed in ((x.home_team, x.home_qb_name), (x.away_team, x.away_qb_name)):
            if team in given or team not in qb1 or team not in last:
                continue
            d, l = qb1[team], last[team]
            if norm(d) == norm(l) and norm(listed) != norm(d):
                print(f"auto QB: {team} schedule lists {listed}, but the depth chart and last start are {l}; using {l}")
                out[team] = l
    # A starter listed Out or Doubtful on this week's injury report does not play: use the
    # depth chart's next QB who is not ruled out (e.g. MIN week 9, Kyler Murray Out).
    try:
        inj = data.load_injuries([season])
        inj = inj[(inj["week"] == week) & inj["report_status"].isin(["Out", "Doubtful"])]
        hurt = {(t, norm(n)) for t, n in zip(inj["team"], inj["full_name"])}
    except Exception as e:  # the report is a check, never a reason to stop the card
        print(f"note: injury report unavailable for the QB check ({e})")
        hurt = set()
    qbs = depth[depth["pos_abb"] == "QB"].sort_values("pos_rank")
    for x in up.itertuples(index=False):
        for team, listed in ((x.home_team, x.home_qb_name), (x.away_team, x.away_qb_name)):
            if team in given:
                continue
            cur = out.get(team, listed)
            if (team, norm(cur)) not in hurt:
                continue
            nxt = [n for n in qbs.loc[qbs["team"] == team, "player_name"] if (team, norm(n)) not in hurt
                   and norm(n) != norm(cur)]
            if nxt:
                print(f"auto QB: {team} {cur} is OUT/DOUBTFUL on the injury report; using {nxt[0]} (next on depth chart)"
                      " - confirm with news")
                out[team] = nxt[0]
    return out


def cmd_card(args):
    qbs = _qb_overrides(args)
    season = args.season or data.current_season()
    qbs = {**_auto_qbs(season, args.week, qbs), **qbs}
    if qbs and not args.week:
        args.week = int(data.load_games().query("season == @season and result.isna()")["week"].min())
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
    # Tiers are judged against the OPENING line, which is what the spread model was trained
    # and tested on; a pick keeps its tier only while the model's number is still past your
    # line. Held out 2023-2026 at LEAN: 54.7% graded at the closing line this way, vs 48.8%
    # judging P directly against the moved line (2015-2022: 53.2% vs 53.1%).
    opener = games["spread_open"].fillna(games["spread_line"])
    po = spread.predict(games, opener)

    # Last QB to start for each team; a listed starter who differs needs checking.
    played = df[df["result"].notna()].sort_values("gameday")
    last_qb = {}
    for g in played.itertuples(index=False):
        last_qb[g.home_team], last_qb[g.away_team] = g.home_qb, g.away_qb

    rows = []
    nfl_checks = checks.NFLChecks(season, week, args.refresh)
    unverified = checks.Unverified()
    print(f"\n{season} week {week} card  (bet rows marked STRONG / LEAN; P = chance the bet wins;"
          f" models = how many of {len(model.LEARNERS)} agree)\n")
    for (_, g), (_, s), (_, t), (_, o) in zip(games.iterrows(), ps.iterrows(), pt.iterrows(), po.iterrows()):
        print(f"{g.away_team} @ {g.home_team}  {g.gameday:%a %m/%d} {g.gametime} ET  ({g.away_qb} vs {g.home_qb})")
        qb_flags = [f"{t} lists {q} but {last_qb[t]} started last game" for t, q in
                    ((g.away_team, g.away_qb), (g.home_team, g.home_qb))
                    if t in last_qb and last_qb[t] != q and t not in qbs]  # --qb confirms it
        for f in qb_flags:
            print(f"   QB CHECK: {f}; the spread pick assumes {f.split(' lists ')[1].split(' but')[0]} plays")
        nfl_checks.show(df, g, last_qb, qbs, o.line, s.line, unverified)
        picks = []
        if not np.isnan(s.p):
            # Side and tier from the opener while the model is still past your line; once the
            # line has moved through the model's number, the side flips to the model's side of
            # your line at PICK.
            open_side = 1 if o.p >= 0.5 else -1
            still = (s.rating - s.line) * open_side >= 0
            if still and not np.isnan(o.p):
                label, prob = _side(o.p, g.home_team, g.away_team, s.line, "spread")
                tier = _tier(max(o.p, 1 - o.p), o.agree, o.n_models)
            else:
                label, prob = _side(s.p, g.home_team, g.away_team, s.line, "spread")
                tier = ""
            if o.line != s.line:
                moved = "past the model's number" if not still else "model still past it"
                print(f"   line   {moved}")
            if tier and qb_flags:
                tier = "HOLD (QB check)"
            each = "  ".join(f"{n} {g.home_team} {-s[f'rating_{n}']:+.1f}" for n in model.LEARNERS)
            shown = tier or "PICK"  # every game gets the model's side; STRONG/LEAN are the tested tiers
            agree = o.agree if still else s.agree
            print(f"   spread {label:14} P {prob:.0%}  models {int(agree)}/{int(s.n_models)}  ({each})  {shown}")
            picks.append(("spread", s.line, label, prob, tier))
            dog, dog_line = (g.home_team, -s.line) if s.line < 0 else (g.away_team, s.line)
            if TEASER_DOG[0] <= dog_line <= TEASER_DOG[1]:
                teased = s.line - TEASER_PTS if s.line < 0 else s.line + TEASER_PTS
                tlabel = f"{dog} +{dog_line + TEASER_PTS:g} (teaser)"
                print(f"   teaser {tlabel}  6-pt leg on a +1 to +2.5 dog: 76-79% since 2009 (2-team at -120 needs 74%)")
                picks.append(("teaser", teased, tlabel, 0.77, "TEASER"))
        else:
            print("   spread: no line yet")
        if not np.isnan(t.line):
            lean = "Over" if t.p >= 0.5 else "Under"
            level = t.rating - total.center
            print(f"   total  {lean} {t.line:g}: model {level:.1f}  P {max(t.p, 1 - t.p):.0%}  PICK")
            picks.append(("total", t.line, f"{lean} {t.line:g}", max(t.p, 1 - t.p), None))
            if not g.dome and (g.wind >= WEATHER_UNDER_WIND or g.rain or g.snow):
                why = f"wind {g.wind:.0f} mph" if g.wind >= WEATHER_UNDER_WIND else "rain/snow forecast"
                print(f"   note   {why}: such games went Under 53-67% in 2009-2023 but only 49-52% since 2024")
            elif g.inj_def_sum >= DEF_INJURY_WATCH:
                print(f"   total  Over {t.line:g}  heavy defensive injuries: watch only, not a bet")
        for kind, ln, label, prob, tier in picks:
            rows.append({"season": season, "week": week, "game_id": g.game_id, "kind": kind,
                         "kickoff": f"{g.gameday:%Y-%m-%d} {g.gametime}",
                         "home_team": g.home_team, "away_team": g.away_team, "line": ln, "pick": label,
                         "p": round(prob, 3), "tier": tier,
                         "bet": tier in ("STRONG", "LEAN"), "qb_check": bool(qb_flags)})
    unverified.show()
    _best_bets(pd.DataFrame(rows))
    _save_picks(pd.DataFrame(rows), PICKS / f"{season}_wk{week:02d}.csv", args.force)


def _best_bets(rows: pd.DataFrame, n: int = 6, college: bool = False):
    """Bets split by evidence (audit, Nov 2026, graded against the CLOSING line you actually bet):
    BACKED = 6-point teaser legs on +1 to +2.5 NFL underdogs (79% in 2023-26, break-even ~74%) and
    the model's LEAN/STRONG spreads while the model is still past your line (55-56% vs the close in
    2023-26; STRONG was no better than LEAN, 51-53%, so they are one tier). Everything else is FUN
    ONLY. College has nothing backed (its picks went 30-41 in 2026)."""
    if rows.empty:
        return
    tier = rows["tier"].fillna("") if "tier" in rows else pd.Series("", index=rows.index)
    backed = rows[tier.isin(["STRONG", "LEAN", "TEASER"])] if not college else rows.iloc[0:0]
    print("\nBACKED BETS (held up out of sample, against closing lines)")
    if backed.empty:
        print("  none on this card" + (" - college picks have no proven edge" if college else ""))
    else:
        b = backed.assign(order=(backed["tier"] != "TEASER").astype(int)).sort_values(["order", "p"],
                                                                                         ascending=[True, False])
        for i, x in enumerate(b.itertuples(index=False), 1):
            label = "TEASER LEG" if x.tier == "TEASER" else "SPREAD"
            print(f"  {i}. {x.pick:18} {x.away_team} @ {x.home_team}  {label}")
        print("  Teaser legs on +1 to +2.5 dogs hit 79% (2023-26; a 2-team teaser at -120 needs 74%).")
        print("  Model spreads hit 55-56% vs the closing line (2023-26; -110 needs 52.4%) - smaller edge, smaller stake.")
    fun = rows.drop(backed.index).sort_values("p", ascending=False)
    print("\nFUN ONLY (no proven edge - small stakes or skip)")
    for i, x in enumerate(fun.head(n).itertuples(index=False), 1):
        print(f"  {i}. {x.pick:16} {x.away_team} @ {x.home_team}  P {x.p:.0%}")
    print("  Not backed: teasing favorites of -7.5 to -8.5 (62% in 2023-26, a losing bet).")
    print("  Log any combo you recommend: python recs.py add ... ; grade: python recs.py grade")


def _save_picks(rows: pd.DataFrame, path, force: bool = False):
    """Every card is saved so every lean is graded. A pick already saved for a game is kept
    (the first card shown is the one graded) unless --force, which replaces only the games
    on this card; games that have kicked off are never added or replaced."""
    if rows.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if "kickoff" in rows:
        now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
        rows = rows[pd.to_datetime(rows["kickoff"]) > now]
    if path.exists():
        old = pd.read_csv(path)
        key = ["game_id", "kind"]
        if force:  # replace only the games re-run; picks for games already played stay
            old = old[~old.set_index(key).index.isin(rows.set_index(key).index)]
            new = rows
        else:
            new = rows[~rows.set_index(key).index.isin(old.set_index(key).index)]
        rows = pd.concat([old, new], ignore_index=True)
        added = len(new)
    else:
        added = len(rows)
    rows.to_csv(path, index=False)
    print(f"\nsaved {added} new pick(s) to {path.name} (graded by: grade)")


def cmd_grade(args):
    games = data.load_games(args.refresh).set_index("game_id")
    files = sorted(PICKS.glob("*.csv"))
    if not files:
        print("no saved cards yet (run: python run.py card --save)")
        return
    log = pd.concat([pd.read_csv(f) for f in files])
    out = []
    for r in log.itertuples(index=False):
        g = games.loc[r.game_id]
        if np.isnan(g.result):
            res = "pending"
        else:
            ats = r.kind in ("spread", "teaser")
            actual = g.result if ats else g.total
            home_or_over = r.pick.startswith(r.home_team) if ats else r.pick.startswith("Over")
            diff = (actual - r.line) * (1 if home_or_over else -1)
            res = "push" if diff == 0 else ("win" if diff > 0 else "loss")
        tier = r.tier if isinstance(getattr(r, "tier", None), str) else ("STRONG" if r.bet else "lean")
        out.append({"week": r.week, "kind": r.kind, "pick": r.pick, "p": r.p, "tier": tier, "result": res})
    out = pd.DataFrame(out)
    print(out.to_string(index=False))
    out["group"] = out["kind"] + " " + out["tier"]
    for name, part in [("all", out)] + list(out.groupby("group")):
        w, l = (part["result"] == "win").sum(), (part["result"] == "loss").sum()
        if w + l:
            print(f"{name:16} {w}-{l}  ({w / (w + l):.1%}), units {w * 100 / 110 - l:+.2f} at -110")


LADDER_EDGE = 0.03


def _fair_american(p: float) -> str:
    """American odds that break even at chance p (0.75 -> -300)."""
    return f"{-100 * p / (1 - p):.0f}" if p >= 0.5 else f"+{100 * (1 - p) / p:.0f}"


def _american(odds: str) -> float:
    """Implied probability of American odds (+150 -> 0.40, -120 -> 0.545)."""
    o = float(odds)
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def cmd_props(args):
    games = data.load_games(args.refresh)
    season = args.season or data.current_season()
    upcoming = games[(games["season"] == season) & games["result"].isna()]
    week = args.week or int(upcoming["week"].min())
    given = _qb_overrides(args)
    games = pipeline.starters(games, {**_auto_qbs(season, week, given), **given}, season, week)
    # The same pre-bet checks as the card: QB, injury report, weather (with its age).
    nfl_checks, unverified = checks.NFLChecks(season, week, args.refresh), checks.Unverified()
    wk = games[(games["season"] == season) & (games["week"] == week)]
    if args.team:
        teams = [t.upper() for t in args.team]
        wk = wk[wk["home_team"].isin(teams) | wk["away_team"].isin(teams)]
    print(f"\n{season} week {week} game checks")
    for g in wk.itertuples(index=False):
        nfl_checks.brief(g, unverified)
    unverified.show()
    # Weather inputs: observed rain/snow/wind for played games (2009+ weather text), the
    # kickoff forecast for upcoming ones. Rain cut QB passing yards ~20-26 below their norm.
    from nflmodel import features
    games = features.weather(games, data.load_game_weather(range(model.FIRST_TRAIN_SEASON, season + 1)),
                             pipeline.forecasts())
    # Pass rush, missed tackles and receiver separation for each team (nflmodel.extra)
    from nflmodel import extra
    games = games.merge(extra.build(games, data.load_team_pbp(range(2015, season + 1))), on="game_id", how="left")
    pg = props.load_player_games(args.refresh)
    up = props.upcoming(pg, games, season, week, data.load_injuries([season], args.refresh),
                        lineups.load_depth(season, args.refresh))
    d = props.build(pd.concat([pg, up], ignore_index=True), games)
    models = props.fit(d[d["td"].notna()])
    today = d[d["td"].isna()].copy()
    today["p"] = props.predict(models, today)
    today["p_first"] = statprops.first_td(today)  # over everyone in the game, before any team filter
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
            line = (f"   {r.player_display_name:24} {r.position:2}  P {r.p:.0%}  fair odds {fair:+.0f}"
                    f"   first TD {r.p_first:.0%} (fair {100 / r.p_first - 100:+.0f})")
            book = odds.get(r.player_display_name.lower())
            if book:
                edge = r.p - _american(book)
                line += f"  | book {book} ({_american(book):.0%})  edge {edge:+.0%}  {'VALUE' if edge >= PROP_EDGE else ''}"
            print(line)
    print(f"\nProbabilities are calibrated (2016-2026 walk-forward), but there is no free archive of prop odds,"
          f" so profit against books is untested. VALUE = model beats the book's implied chance by {PROP_EDGE:.0%}+.")
    if args.no_ou:
        return
    wk = games[(games["season"] == season) & (games["week"] == week)]
    qbs = {**dict(zip(wk["home_team"], wk["home_qb_name"])), **dict(zip(wk["away_team"], wk["away_qb_name"]))}
    _ou_props(args, d, today, qbs)


def _ou_props(args, d, today, qbs):
    """Over/under markets: projection, and P(over) for any --line given."""
    lines = {}
    for item in args.line or []:  # "CeeDee Lamb:receptions=5.5", ladder "Jordan Love:passing_yards=175+@-250"
        who, val = item.rsplit("=", 1)
        name, market = who.rsplit(":", 1)
        price = None
        if "@" in val:
            val, price = val.split("@")
        val = val.strip()
        ln = float(val[:-1]) - 0.5 if val.endswith("+") else float(val)
        lines[(name.strip().lower(), market.strip())] = (ln, price)
    done = d[d["td"].notna()]
    hist_from = int(done["season"].max()) - 2
    markets = args.market or list(statprops.MARKETS)
    today = statprops.prepare(today)
    scan_rows = []
    for market in markets:
        stat, pos = statprops.MARKETS[market]
        pre = statprops.prepare(done)
        rows = pre[pre["position"].isin(pos) & (pre["games"] >= 1)]
        seed = statprops.StatModel(market).fit(rows[rows["season"] < hist_from], rows.iloc[:0].assign(proj=0.0))
        hist = rows[rows["season"] >= hist_from].assign(proj=lambda x: seed.project(x))
        sm = statprops.StatModel(market).fit(rows, hist)
        cand = today[today["position"].isin(pos)]
        if cand.empty:
            continue
        cand = cand.assign(proj=sm.project(cand))
        cand = cand[cand["proj"] >= {"passing_yards": 100, "rushing_yards": 15, "receiving_yards": 15,
                                     "passing_tds": 0.3}.get(market, 1)]
        # one quarterback per team, the same in every market: the game's listed starter (as on
        # the card, or --qb), else the QB with the biggest projected role. Choosing per market
        # showed different QBs for one team (e.g. a backup in passing yards, starter in completions).
        qb = cand["position"] == "QB"
        listed = cand["player_display_name"].str.lower() == cand["team"].map(qbs).astype(str).str.lower()
        has_listed = cand[qb & listed]["team"].unique()
        top = cand[qb & ~cand["team"].isin(has_listed)].sort_values("proj").groupby("team").tail(1).index
        cand = cand[~qb | (listed & qb) | cand.index.isin(top)]
        if args.scan and market in ("receiving_yards", "rushing_yards", "passing_yards"):
            scan_rows += _scan(args, market, cand.assign(proj=cand["proj"].values), sm)
        print(f"\n{market.replace('_', ' ')}  (median = model's fair line; P = chance of going over the line you gave)")
        for r in cand.sort_values(["team", "proj"], ascending=[True, False]).itertuples(index=False):
            med = sm.median(r.position, r.proj, getattr(r, 'spread_for', None))
            out = f"   {r.team:3} {r.player_display_name:24} {r.position:2}  median {med:6.1f}"
            got = lines.get((r.player_display_name.lower(), market))
            if got is not None:
                ln, price = got
                po = sm.p_over(r.position, r.proj, ln, getattr(r, 'spread_for', None))
                side, ps = ("Over", po) if po >= 0.5 else ("Under", 1 - po)
                out += f"  | {side} {ln:g}: {ps:.0%} (fair {_fair_american(ps)})"
                if price:
                    edge = ps - _american(price)
                    out += f"  DK {price} ({_american(price):.0%})  edge {edge:+.0%}  {'VALUE' if edge >= LADDER_EDGE else 'no value'}"
                elif ps >= OU_VALUE:
                    out += "  (add @price to check value)"
            print(out)
    if args.scan:
        _print_scan(scan_rows)
    print(f"\nVALUE = model chance beats DK's implied chance by {LADDER_EDGE:.0%}+. Yardage ladders were calibrated"
          " out of sample in 2023-26 (said 70-75%, hit 76%), so the model's chance is if anything low."
          " Give prices as \"Name:market=40+@-250\".")


def cmd_odds(args):
    """DraftKings' over/yes legs with the sharp books' no-vig chance for the same bet. A positive
    edge means DraftKings pays more than the sharp market thinks the bet is worth."""
    from nflmodel import odds
    if not odds.key():
        raise SystemExit("ODDS_API_KEY is not set: add it in the environment's settings, then start a new session")
    ev = odds.find_event(args.league, args.team)
    if ev is None:
        raise SystemExit(f"no upcoming {args.league} game found for {args.team}")
    cmp = odds.compare(odds.props(args.league, ev))
    if cmp.empty:
        print("no DraftKings props posted for this game yet")
        return
    has = cmp[cmp["sharp_fair"].notna()].sort_values("edge_vs_sharp", ascending=False)
    print(f"DraftKings legs priced by sharp books too ({len(has)} of {len(cmp)}); edge = sharp fair - DK implied")
    for r in has[has["edge_vs_sharp"] >= args.min_edge].itertuples(index=False):
        pt = "" if pd.isna(r.point) else f"{r.point + 0.5:g}+" if r.market != "anytime_td" else ""
        flag = "VALUE" if r.edge_vs_sharp >= 0.03 else ""
        print(f"  {r.player:24} {r.market:16} {pt:6} DK {r.price:+5.0f} ({r.dk_implied:.0%})  "
              f"sharp {r.sharp_fair:.0%} [{r.sharp_books}]  edge {r.edge_vs_sharp:+.0%}  {flag}")
    print("\nCheck legs with the model too: run.py props --line \"Name:receiving_yards=40+@-250\"")


def cmd_parlay(args):
    """Is a (boosted) parlay worth it? Uses the chances you give (model or sharp)."""
    from nflmodel import odds
    legs = []
    for x in args.leg:
        q, price = x.split("@")
        q = float(q.rstrip("%")) / (100 if q.endswith("%") or float(q.rstrip("%")) > 1 else 1)
        legs.append((q, float(price)))
    p, pay, ev = odds.parlay_ev(legs, args.boost / 100)
    dec = pay - 1
    am = f"+{dec * 100:.0f}" if dec >= 1 else f"-{100 / dec:.0f}"
    print(f"chance {p:.1%}  pays {am} (decimal {pay:.2f}{f', with +{args.boost:g}% boost' if args.boost else ''})")
    print(f"expected return {ev:+.1%} per $1  -> {'GOOD BET' if ev > 0 else 'losing bet'}"
          " (legs in one game are treated as independent; same-game legs that help each other are a bit better)")


def _scan(args, market, cand, sm):
    """Each DK ladder rung for this market: model chance, sharp-anchored chance, DK's price."""
    from nflmodel import odds
    if not hasattr(_scan, "cache"):
        _scan.cache = odds.ladders("nfl", args.scan)
    dk, sh = _scan.cache
    if dk.empty:
        return []
    norm = lambda s: lineups._norm(pd.Series([s]))[0]
    dk = dk[dk["market"] == market].assign(key=lambda x: x["player"].map(norm))
    sh = sh[sh["market"] == market].assign(key=lambda x: x["player"].map(norm))
    out = []
    for r in cand.itertuples(index=False):
        k, sf = norm(r.player_display_name), getattr(r, "spread_for", None)
        rungs = dk[dk["key"] == k]
        if rungs.empty:
            continue
        shape = None
        main = sh[sh["key"] == k]
        if len(main) and float(main["point"].iloc[0]) >= 19.5:  # tiny main lines (a TE at 7.5) stretch badly
            # Sharp-anchored chances: the shape of outcomes (actual / projection) for players
            # projected near the sharp main number, pooled over 7 neighbouring bins so one noisy bin does not
            # decide it, scaled so the chance at the sharp books' main number equals their no-vig
            # chance; the other rungs are read off that scaled shape.
            L, q = float(main["point"].iloc[0]), float(main["fair"].iloc[0])
            (ed, vals), _ = sm._dist(r.position, sf)
            i = int(np.clip(np.searchsorted(ed, L, side="right") - 1, 0, len(vals) - 1))  # players projected near the market's number
            js = range(max(0, i - 3), min(len(vals), i + 4))
            ratio = np.concatenate([vals[j] / max((ed[j] + ed[j + 1]) / 2, 1.0) for j in js])
            qv = np.quantile(ratio, 1 - q)
            if qv > 0:
                shape = ratio * (L / qv)
        for x in rungs.itertuples(index=False):
            pm = sm.p_over(r.position, r.proj, x.point, sf)
            ps_ = float((shape > x.point).mean()) if shape is not None else np.nan
            out.append((r.team, r.player_display_name, market, x.point + 0.5, x.price, x.implied, pm, ps_))
    return out


def _print_scan(rows):
    if not rows:
        return
    df = pd.DataFrame(rows, columns=["team", "player", "market", "rung", "price", "dk", "model", "sharp"])
    df["e_model"], df["e_sharp"] = df["model"] - df["dk"], df["sharp"] - df["dk"]
    df["best"] = df[["e_model", "e_sharp"]].min(axis=1, skipna=False)
    df = df[(df["e_model"] >= LADDER_EDGE) | (df["e_sharp"] >= LADDER_EDGE)]
    df = df[(df["price"] >= -600) & (df["price"] <= 400)]
    print("\nDraftKings ladder rungs with an edge (model = our projection; sharp = Pinnacle/FanDuel main line"
          " stretched to this rung; BOTH = both beat DK by 3%+, the ones to bet):")
    if df.empty:
        print("  none")
        return
    df = df.sort_values(["best", "e_model"], ascending=False)
    for r in df.itertuples(index=False):
        both = "BOTH" if r.e_model >= LADDER_EDGE and r.e_sharp >= LADDER_EDGE else (
            "model only" if r.e_model >= LADDER_EDGE else "sharp only")
        sh = "  n/a" if pd.isna(r.sharp) else f"{r.sharp:4.0%}"
        print(f"  {r.team:3} {r.player:22} {r.market:15} {r.rung:g}+ DK {r.price:+5.0f} ({r.dk:.0%})  "
              f"model {r.model:.0%}  sharp {sh}  {both}")


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
    c.add_argument("--save", action="store_true", help="no longer needed: every card is saved for grading")
    c.add_argument("--force", action="store_true", help="replace an already-saved card")
    sub.add_parser("grade")
    pr = sub.add_parser("props")
    pr.add_argument("--season", type=int)
    pr.add_argument("--week", type=int)
    pr.add_argument("--team", action="append", help="only these teams, e.g. --team SF --team ATL")
    pr.add_argument("--odds", action="append", help='your book\'s anytime TD odds, e.g. "George Kittle=+120"')
    pr.add_argument("--min-p", type=float, default=0.15, help="hide players below this chance")
    pr.add_argument("--market", action="append", choices=list(statprops.MARKETS),
                    help="over/under markets to show (default: all)")
    pr.add_argument("--line", action="append", help='book line, e.g. "CeeDee Lamb:receptions=5.5"')
    pr.add_argument("--no-ou", action="store_true", help="anytime/first TD only")
    pr.add_argument("--qb", action="append", help='confirmed starter, e.g. BAL="Tyler Huntley"')
    pr.add_argument("--scan", help="price every DraftKings ladder rung for this team's game (odds API), e.g. Bears")
    pa = sub.add_parser("parlay", help="parlay chance and expected return, with a DK profit boost")
    pa.add_argument("--leg", action="append", required=True, help='chance@price, e.g. "0.72@-134" or "72%%@-134"')
    pa.add_argument("--boost", type=float, default=0.0, help="profit boost in percent, e.g. 30")
    ln = sub.add_parser("lineup")
    ln.add_argument("--season", type=int)
    ln.add_argument("--week", type=int)
    ln.add_argument("--team", action="append")
    od = sub.add_parser("odds", help="DraftKings prop prices vs the sharp books (needs ODDS_API_KEY)")
    od.add_argument("--team", required=True, help="either team, e.g. Bears")
    od.add_argument("--league", choices=["nfl", "cfb"], default="nfl")
    od.add_argument("--min-edge", type=float, default=0.0)
    args = ap.parse_args()
    {"backtest": cmd_backtest, "card": cmd_card, "grade": cmd_grade, "props": cmd_props,
     "lineup": cmd_lineup, "odds": cmd_odds, "parlay": cmd_parlay}[args.cmd](args)


if __name__ == "__main__":
    main()
