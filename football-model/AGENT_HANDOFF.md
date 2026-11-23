# Handoff for a new agent - NFL betting model (written Nov 15 2026, ~1:20 CT)

You are taking over from a previous agent. The owner, Chris, was not satisfied with the previous work.
Read this file, then `CLAUDE.md` (his standing rules), then the code. Nothing here is a guess: every
number names the script that produced it. Re-run a script before you quote its number.

## 1. What Chris wants
- He bets $3 per pick on DraftKings (DK): sides, totals, teasers, prop parlays.
- He wants a model that WINS, a pick on every game, and prop parlays. His words today: "there has to
  be a way to win", "this model is flawed", "every game is no bet", "you aint cutting it".
- The previous agent's answer was, in short, "sides and totals at -110 have no tested edge; only
  teasers on small dogs and one Under rule do". He does not accept that as a finished answer.
  Your job is to find something better or to prove more convincingly what is and is not possible.
  Do not just repeat the previous conclusion at him.

## 2. His rules (full text in CLAUDE.md - they are binding)
1. No guessing. Every number comes from a tool's output or a tested result, and you say which.
2. No gut overrides of a tool's output. Skip a pick only for a named failed check.
3. If unsure what he means, ask.
4. Plain, short answers. No unders on player props (DK ladders are overs). No rush-attempt props.
   Receptions OK. Game-total unders OK.
5. A pick on EVERY game (spread, winner, total). Always show tested records for both periods
   (2015-22 / 2023-26). He does NOT bet early in the week (injuries change) - never suggest it and
   never quote opening-line records as if they apply to him.
6. Card layout he asked for today: pick on every game, tested teaser legs marked, every surprise
   change flagged (QB, injuries, line moves, weather).

## 3. Where things are
- Repo `g5dsfss7yk-debug/chrisgantt-site`, folder `football-model/`.
- **All current work is on branch `claude/pensive-wright-l3v5cy`.** Branch `claude/football-model`
  is one session behind (Chris has not approved pushing there).
- Setup: `pip install scikit-learn pyarrow` (pandas/numpy present). Run from `football-model/` with
  `PYTHONPATH=.`. Data downloads itself into `data/` (gitignored) from nflverse, nfelo, ESPN, Open-Meteo.
- Odds: The Odds API, key in env `ODDS_API_KEY` or `DDS_API_KEY`. **About 6-9 credits left this month
  (500/month). A props pull costs about 11 per game.** `--cached` reuses saved prices, but in a fresh
  container there is no cache and it WILL call the API. This is the main practical bottleneck.
- `api.collegefootballdata.com` is authenticated by the session proxy (college data).

| File | What it is |
|---|---|
| `v2/nfl.py` | Game model: exponentially weighted play-by-play team ratings -> standardized ridge on margin / total, with the line as a feature |
| `v2/card.py` | Weekly card vs DK lines: pick on every game, `>> TEASER LEG`, `** CHANGE` flags |
| `v2/props.py`, `v2/props_card.py` | Player prop model and card vs DK ladders |
| `v2/test_nfl.py`, `v2/test_teaser.py`, `v2/improve.py` | Walk-forward tests of the game model |
| `v2/dig.py` | Today's search for a game-day edge (five pre-stated ideas, three periods) |
| `audit/v2_vs_dk.py` | Grades saved DK prop prices (`picks/rungs_v2/`) against box scores |
| `audit/rule_scan.py`, `audit/market_error_model.py` | Earlier searches (966 rules; a model of closing-line errors) |
| `recs.py`, `picks/recs.csv` | Log of every recommended bet, with grading |
| `README.md` | Long history of everything tested. Sections "V2 flaws", "V2 fixes Nov 15", "Dig for a game-day edge" are current |
| `nflmodel/`, `run.py` | OLD model, scratched Nov 15. Still supplies data loaders (`nflmodel/data.py`), odds, live model |

## 4. What is tested (walk-forward, graded at the game-day closing line; break-even 52.4% at -110)
From `v2/test_nfl.py` / `v2/improve.py`, 2015-22 / 2023-26:
- Spread, all games: 52.4% / 50.7%. Edge 1+ pts: 52.8% of 849 / 55.0% of 311. Edge 2+: 57.0% of 214 / 58.1% of 62.
- Total, all games: 53.2% / 51.7%. Edge 1+: 55.8% / 50.8%. Model still picks Over in 61% of 2023-26 games.
From `v2/dig.py`, 1999-2014 / 2015-22 / 2023-26:
- **6-point teaser leg on every dog +1.5..+2.5 (no model): 72.7% of 395 / 77.0% of 283 / 77.3% of 207.**
  Game total <= 44: 75.9% / 77.4% / 78.9%. A 2-team teaser at -120 needs 73.9% per leg.
  Same-week 2-team teasers of these dogs: 55.0% / 60.6% / 63.8% (break-even 54.5% at -120).
  The model's own dog picks did WORSE (69.7% in 2015-22), so legs are chosen without the model.
  **DK's real teaser price has never been checked by a tool.** That is an open hole.
- Rejected: dogs +3 (66.7% in 2023-26), favorites -7.5..-8.5 (63.2%), moneylines by price range,
  fading lines that stray from market-implied ratings, nfelo vs the close (47-51% since 2023).
From `audit/rule_scan.py` (earlier session): home QB change -> Under 56.5% / 54.5% (457 games).
From the old model (README "BET EARLY"): 56.7% / 57.1% against the OPENING line. Chris refuses to bet early.
Props (`audit/v2_vs_dk.py`): only one game graded (NE@DET, 788 rungs). Rungs where the model was 3%+ above
DK: 47 rungs, 4 hits, large loss. Rungs where the model was below DK: 476, hit 36.1% vs DK-implied 48.0%.
One game is far too little; no conclusion yet.
Chris's placed record before today (`recs.py`): 3-12, net -$30.

## 4b. Added Nov 23 (v2/test_three.py, v2/test_four.py; README "Three gaps tested", "Four more inputs tested")
- Spreads now use the starting QB's own value + red-zone TD rate + competitive plays only (garbage time out):
  all games 52.6% / 54.4%, edge 1+ 55.0% of 1046 / 53.1% of 420.
- Totals now use pass rushers listed Out/Doubtful: all games 53.5% / 51.0%.
- Tested and not used: opponent adjustment, special teams by unit, referee crew, pace/pass rate, backup RB/WR/TE share.
- Props now use targets/carries freed up by teammates Out/Doubtful (fixed a +2-3% under-rating of those players).
- Fresh container: v2/test_alt.py must run once (makes v2/resid_*.npy) before props_card.py works.

## 5. What the previous agent fixed today (so you do not redo it)
- Wind was missing in the schedule data (every game since 2026 week 5) and read as 0 mph -> totals
  model picked Over in 100% of those games. Now filled from play-by-play text / forecast.
- Ridge features were unscaled, so rate stats (EPA, success rate, pressure) were shrunk to nothing.
- Card fit the spread model on the opener but picked against the game-day line. Now fit on the game-day line.
- QB-change flag fired for games with no starter listed; card priced in-progress games off live lines.

## 6. Known weaknesses and honest criticism of the work so far
- The game model is a thin layer on top of the line (the line is a feature and dominates). It has no
  player-level information: no QB quality, no injuries, no lineups. It mostly restates the market.
- Everything was graded at the CLOSING line only. Nothing measures the line Chris actually gets
  (DK, hours before kickoff) or closing-line value of his real bets.
- Many variants were tried across sessions on the same 2015-26 data; survivors may be luck.
- Props, the market most likely to be soft, have almost no evidence because there is no price archive
  and almost no API credits.
- Card QB names come from nflverse and can be stale. Today ESPN listed Darnold (SEA) Out and Minshew (ARI)
  and Huntley (BAL) on injured reserve while the schedule had them starting. The `** CHANGE` lines flag
  this but the model does not adjust.
- `props_card.py` alt spreads still fit on the opener and were not re-calibrated after the scaling fix.

## 7. Directions not yet tried (ideas, NOT results - test before telling Chris anything)
1. **Price, not prediction.** Compare DK's price with sharp books' no-vig price (Pinnacle etc. via the
   Odds API, `nflmodel/odds.py`) and bet only where DK is off. Needs credits: ask Chris about a paid
   Odds API tier, which also has HISTORICAL odds (props 2023+) - that would allow a real backtest of
   props and of game-day lines hours before kickoff, the two things never tested.
2. **DK boosts and promos.** `run.py parlay --boost` computes the value. Never measured over time.
3. **Check DK's actual teaser prices and rules** (2-team 6-pt price, ties, which lines qualify).
4. **Timing inside game day.** Chris will not bet early in the week, but betting after inactives
   (90 minutes before kickoff) versus Sunday morning is untested. Needs intraday line snapshots.
5. **Player-level game model.** QB-adjusted ratings and injury-adjusted lineups, tested at the close.
   Earlier sessions say injuries added nothing vs the close (README "Variables tested and left out").
6. **Live betting.** `nflmodel/live.py` was audited as calibrated for live prop ladders (README), never
   tested for profit against DK's live prices.
7. **Derivative markets** (alt lines, team totals, first half) priced off the main line by formula.
8. **Keep saving DK prop prices every week** (`picks/rungs_v2/`) so `audit/v2_vs_dk.py` gains sample.

## 8. Open items right now (Nov 15)
- NE@DET final: DET 35-10. Bets #166, #174, #176, #181 lost.
- #160 CLE Under 40.5: Watson started (ESPN box score) - condition met, game in progress.
- #161 LV Under 40.5 (3:05 CT): only if Mendoza starts; LV inactives were not posted at 12:40 CT.
- #162 BAL Under (Monday): only if Huntley starts - ESPN lists him on injured reserve, unresolved.
- Late card from DK prices saved 12:45 CT: LV +6.5 / Under 40.5; LA -9.5 / Over 38.5; SF -4.5 / Under 55.5;
  CIN -3.5 / Over 49.5; BAL -4.5 / Under 38.5. No dog +1.5..+2.5 among them.
- After about 3:30 CT: `PYTHONPATH=. python audit/v2_vs_dk.py` (slow, 10+ minutes - run in background) to
  grade the 8 early games' prop prices, then `python recs.py grade`.
- Ask Chris which of today's bets he placed (`python recs.py placed`).
- Ask Chris whether this branch should be pushed to `claude/football-model`.

## 9. How to talk to Chris
Short, plain, no jargon. Give the pick and its tested record. Say "I don't know" when no tool gives
the number. He is frustrated with hearing "no edge" - if that is still the truth after you test
something new, show the test in two lines and say what you will try next, not a lecture.
