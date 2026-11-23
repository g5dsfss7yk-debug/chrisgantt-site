# NFL betting model

Rates every NFL game from free public data and judges each rating against the betting
line, producing a weekly card with calibrated win probabilities.

```
pip install -r requirements.txt
python run.py card --save       # this week's card, saved to picks/ for grading
python run.py card --week 7 --line MIN=-5.5   # judge your book's number instead
python run.py grade             # record of every saved card vs final scores
python run.py backtest          # walk-forward test, tuned 2015-2022, held out 2023+
```

## How it works
1. **Rating (stage 1).** Three different learners (ridge regression, gradient-boosted
   trees, extra-randomized trees) each predict the home margin from football features,
   never seeing a betting line. Their average is the rating; the card shows how many of
   the three land on the same side of the line.
2. **Edge (stage 2).** The market is usually right, so only part of the gap between the
   rating and the line is real. A logistic regression, fit on out-of-sample ratings from
   earlier seasons, turns that gap into the probability the bet wins. These are
   calibrated: picks the model gives 57% have won about 57-61%.
3. **Timing.** Spreads are judged against the **opening line** using only information
   known when lines open; lines tend to move toward the model during the week. Totals
   are judged on game day, when the forecast and final injury report are in.
4. **Card.** Spread bets need all three models on the same side: STRONG at P >= 55%,
   LEAN at P >= 53%. Picks are held when the listed QB differs from last week's starter.
   Every game gets a spread PICK and a total PICK (the model's side); STRONG/LEAN mark the
   tested spread tiers, and the card ends with its picks ranked. Wind/rain is noted and heavy
   defensive injuries are flagged as an Over to watch. Every card is saved to picks/: the
   first pick shown for a game is kept (re-running adds new games only, `--force` replaces),
   games that have kicked off are never added, and `grade` scores every pick by kind and tier.

Backtest against opening lines (`python run.py backtest`):

| Tier | 2015-2022 | 2023-2026 (held out) |
|---|---|---|
| STRONG | 147-88 (62.6%) | 69-54 (56.1%) |
| LEAN | 329-239 (57.9%) | 177-131 (57.5%) |

Model totals are information only. Walk-forward, the model's side won 51.0% (2015-19),
49.5% (2020-23) and 49.9% (2024-26). Until November 2026 the card took its Over/Under side
from the raw rating, which runs about a point below recent scoring, so it leaned Under in
most games while Overs were hitting (Unders went 47% in 2024-26; the model's Under leans
won 45.8%). The side now comes from the rating re-leveled by its recent miss against actual
scores, which splits Over/Under about evenly.

Common Under angles that worked in 2017-2023 did not hold up in 2024-2026 (Under rate):

| Situation | 2009-16 | 2017-23 | 2024-26 |
|---|---|---|---|
| Outdoor wind 15+ mph | 52.8% | 59.9% | 48.6% |
| Outdoor rain/snow | 46.5% | 66.7% | 51.7% |
| Total 50+ | 49.4% | 53.7% | 45.7% |
| Division game | 53.6% | 53.0% | 45.7% |
| Backup QB starts | 52.4% | 53.9% | 47.0% |
| Spread 10+ | 52.6% | 53.6% | 40.7% |
| All games | 49.5% | 52.8% | 47.3% |

## Anytime-TD props (`python run.py props`)
```
python run.py props --team SF --team ATL --odds "George Kittle=+120" --odds "Bijan Robinson=-150"
```
P(rushing or receiving TD) for every RB/WR/TE/QB with a touch in his team's last two games, minus
players listed Out or Doubtful. Features: share of the team's red-zone (inside 20) and goal-line
(inside 5) touches, carry and target share, touches, recent TD rate, team implied points from the
spread and total, opponent TDs allowed, home, position (gradient boosting + logistic, averaged).

Also: offensive snap share, targets and carries vacated by teammates who are out, the opponent's
TDs allowed to the player's position, and wind. Walk-forward 2016-2026: log loss 0.450 vs 0.476
for a player-TD-rate baseline (2016-2022) and 0.431 vs 0.459 (2023-2026, held out); the added
inputs improved both periods (0.4517 -> 0.4501, 0.4328 -> 0.4310). Calibrated: players given 30-40% scored 36-38%. No free
archive of historical prop odds exists, so profit against books is untested; a prop is flagged
VALUE only when the model beats the book's implied chance by 5+ points, to clear the hold.

## Over/under props and first TD (same `props` command)
```
python run.py props --team DAL --line "CeeDee Lamb:receptions=5.5" --line "Dak Prescott:passing_yards=245.5"
```
Markets: receptions, receiving yards, rush attempts, rushing yards, passing yards, passing TDs,
completions. A gradient-boosted projection per market (running averages, shares, snap rate,
vacated work, opponent allowed to the position, implied points, spread, wind) and an empirical
outcome distribution from out-of-sample projections give the median (fair line) and P(over).

Walk-forward 2019-2026 (mean absolute error, model vs the player's season average): passing yards
62.2 vs 71.5, completions 5.2 vs 6.0, passing TDs 0.86 vs 0.89, rush attempts 2.9 vs 3.0,
receptions 1.30 vs 1.32, rushing yards 17.4 vs 17.4, receiving yards 17.2 vs 17.2. P(over) is
calibrated within a few points (raw chances ran slightly hot at the ends and are shrunk 12%).
So QB props are where the projection knows most beyond the season average; for receiving and
rushing yards the value is only when a line lags news (injuries, vacated targets). No free
archive of prop lines exists, so profit against books is untested; VALUE needs 57.4%+.
First TD = each player's share of the game's TD rate from the anytime model (untested).

## Variables tested and left out
| Variable | Test | Result |
|---|---|---|
| Missing regulars by unit (snap counts, every absence) | spread vs closing line, 2015-2026 | no change (rating error 9.963 vs 9.964); books price absences |
| Penalties, 4th-down rate, play-calling shift, late-season motivation, home field since 2020, Denver, turf | spread vs opening line | LEAN worse in both periods (57.9 -> 56.2%, 57.6 -> 55.9%), STRONG flat |
| Referee crews, primetime/divisional/Thursday unders | totals | did not hold up across periods |

## Lineups (`python run.py lineup --team DAL`)
Starters at every position from nflverse's daily ESPN depth chart, with Out/Doubtful players
starred, plus every "regular" (50%+ of his unit's snaps over the last two games) who is Out,
Doubtful or no longer on the depth chart (IR, released). Props candidates come from the same
depth chart, so a starter returning from injury is included and a player who left is not. The
card's `--qb TEAM="Name"` rates a game with the confirmed starter when the schedule lags.
Missing regulars are shown, not modeled: the spread model has no backtest with lineups yet.

## Data
| Source | Used for |
|---|---|
| nflverse games | scores, closing lines, roof, surface, rest, QBs, coaches |
| nflverse play-by-play | opponent-adjusted EPA/play and success rate, turnovers, weather text (rain/snow/gusts) |
| nflverse injuries + snap counts | snap-weighted injury burden, roster continuity |
| nflverse weekly rosters | returning and added production |
| nflverse weekly player stats | carries, targets, TDs for props |
| nflverse depth charts | starters at every position, props candidates |
| [nfelo](https://github.com/greerreNFL/nfelo) | opening spreads, independent Elo with QB adjustments |
| `nfl-weather` branch | kickoff forecasts, fetched every 3 hours by `.github/workflows/nfl-weather.yml` |

## Features
| Group | Known at open | Game day only |
|---|---|---|
| Strength | Elo, nfelo, points form, EPA and success rate, turnover and close-game luck | |
| Quarterback | QB value, experience, QB new to team | backup starting |
| Change | returning/added snaps, coach tenure, stale-rating fade | |
| Situation | home field, division, rest, byes, short weeks, travel, time zones | |
| Matchups | explosive plays, red-zone TD rate, special teams, kicking, pass rush vs line | |
| Injuries | | final report by unit (skill, line, pass rush, LB, secondary), clusters, line vs rush |
| Pace and style (totals) | | snap pace, plays per game, neutral pass rate |
| Weather (totals) | | temp, wind, gusts, rain, snow, dome, turf |

## College football (`cfb.py`)
Same two-stage ensemble and the same three learners, on college data:

```
python cfb.py card --line "Iowa=-6.5" --line "TCU=-7.5" --save   # judge your book's numbers
python cfb.py backtest
python cfb.py grade
```

- Data: [cfbfastR-data](https://github.com/sportsdataverse/cfbfastR-data) schedules (scores, neutral site,
  conference, CFBD Elo) and book lines (openers, 2014-2025), plus the ESPN play-by-play release from
  [sportsdataverse-data](https://github.com/sportsdataverse/sportsdataverse-data), reduced to one row per
  team-game and cached in `data/raw/cfb/`.
- Features: opponent-adjusted EPA, success rate, explosive rate, havoc and sacks (garbage time removed),
  margin and points ratings, red-zone TD rate, special teams, turnovers, CFBD Elo, home vs neutral field,
  conference game, rest and byes, FCS opponent, early season, QB changes.
- No free college injury reports or historical weather exist, so neither is a model input; the QB-change
  flag holds a pick for checking.
- The current season's lines are not in the books file, so pass your numbers with `--line`.

Backtest (all three models agree, P >= 55%):

| Line | 2017-2021 | 2022-2025 (held out) |
|---|---|---|
| Opening spread | 219-166 (56.9%) | 54-40 (57.4%) |
| Closing spread | 13-8 | 1-0 (almost never fires) |
| Opening total | 198-172 (53.5%) | 34-35 (49.3%) |
| Closing total | lost | lost |

Model totals are information only. An earlier 54.9% / 56.2% opening-total result came from a
fixed Under lean in stage 2 cancelling the model's high scoring level; with that removed
(totals now centered on the model's recent gap to the line) the edge is gone. The NFL totals fix (re-leveling on actual scores) was
tested here too and not adopted: every-game leans won 50.0% in 2024-26 against 51.5% with the
line centering, and it leaned Under in 58% of 2026 games against 49%. Totals of 65+
are flagged as an Under to watch: 55-56% through 2023, below 52% since.

## Where the edge is (Nov 2026 review)
- **Spreads: bet early.** The spread model's tested edge is against the opening line (LEAN 58-59% in
  every period). Graded at the closing line, every-game picks are about 50% since 2023, and versions
  trained on closing lines with game-day injuries did no better. Closing lines moved toward the
  model's side about twice as often as away from it, so most of the value is gone by Sunday.
- **The card now judges tiers against the opener** and keeps a tier only while the model's number is
  still past your line: 54.7% at LEAN graded at the close in 2023-2026, vs 48.8% judging P directly
  against the moved line.
- **Teaser legs.** 6-point teasers on underdogs of +1 to +2.5 won 76.1% (2009-2022) and 78.8%
  (2023-2026, n=217); a 2-team teaser at -120 needs 73.9% per leg. Favorite legs (-7.5 to -8.5)
  fell to 65% since 2023. The card prints these as TEASER rows and grades them.
- **College.** Against Saturday lines the CFB spread model is about 50% in every period and 44.5% in
  2026 (weeks 1-4 and big underdogs worst). The current season's openers are not in the free data,
  so CFB picks are leans only unless you give an early-week line.

## Pre-bet checks on every card (`checks.py`)
Every game on `run.py card` and `cfb.py card` prints the same checklist, and anything the data
could not confirm is listed under **NOT VERIFIED** at the end of the card:
- **QB**: schedule's listed starter vs the daily depth chart's QB1 vs the last starter, plus the
  QB's injury-report and practice status. If the listed QB disagrees with both and those two agree,
  the card uses them automatically (`auto QB:`); the schedule file can carry an old matchup's QB.
- **Injuries** (NFL): regulars (half the snaps the last two games) who are Out/Doubtful or off the
  depth chart, questionable players, and players who did not practice before game statuses are set.
  College has no free injury report, so it is always listed as NOT VERIFIED.
- **Form**: record, record against the spread, last three games with cover/no cover, rest days
  (bye, short week); college adds power / offense / defense ranks.
- **Weather and field**: kickoff forecast from the weather job (NFL and college), dome, surface.
- **Line**: opener vs your number.
- **Props run the same checks** (`run.py props` prints QB, injury report and weather per game first).
- **Weather freshness and rain risk**: a forecast older than 6 hours is NOT VERIFIED. Any outdoor game
  with a 35%+ precipitation chance (or snow) flags passing and receiving overs, even when the forecast
  amount is ~0: in rain, QBs threw 19-26 yards below their recent average and 200+ yards fell from
  66% to 51% (2020-2026). Rain and snow are also inputs to the over/under prop model; in rain games
  its QB passing-yards projection was 22 yards too high before and 10 after (MAE 56.0 -> 53.1).

## Variables added in the Nov 2026 review
- **Spread**: injuries, backup QB, offensive-line and secondary injury clusters (`LATE_FEATURES`) are now
  in the spread model: LEAN 57.9% -> 59.0% (2015-22), 57.2% -> 57.8% (2023-26). Weather/turf lowered
  spread LEAN in both periods and stay in totals/props only.
- **Props**: rain, snow, cold and turf (TD and over/under models).
- **Live weather**: `data.load_forecasts` fetches Open-Meteo directly (cached an hour), falling back to
  the GitHub weather job.
- **Props usage and matchup**: air-yards share, aDOT, CPOE, the offense's pressure allowed and
  receiver separation, the defense's pass rush and missed tackles (TD model; passing yards,
  completions and receptions).
- **Totals**: referee crew's history vs the total and both offenses' pressure allowed
  (`nflmodel/extra.py`): every-game hit rate 50.3% -> 51.0% (2015-22), 50.2% -> 51.4% (2023-26).
- **Tested and not used**: the other 11 NFL extras (bad throws, drops, missed tackles, CPOE, time to
  throw, aggressiveness, separation, YAC/rush yards over expected, referee home margin) for spreads
  and totals - none helped both periods, alone or together; college travel/time zones for spreads.
- **College totals**: field turf and dome.
- **CollegeFootballData** (`cfbmodel/cfbd.py`, key held by the session proxy): talent, returning
  production, recruiting, transfer portal, new head coach, prior SP+. Tested for spreads and totals
  and not used in the picks (they lowered STRONG in both periods); each college card shows them as a
  `roster:` line.

## Betting rules (audit, Nov 8 2026; re-evaluation Nov 10)

**Re-evaluation (Nov 10).** Audits A-D test whether the model's chances are right across ALL
players. Bets are only placed where the model disagrees with DraftKings, and that is exactly where
it is most likely to be missing something the book knows. A calibrated model can still lose on its
picks. The only test that counts is audit E (`audit/vs_dk.py`): the model's chances against DK's
real prices, graded on results. There was no archive of DK prices, so it starts now:
`run.py props --week N --scan all` before each slate (about 7 odds-API credits a game, ~100 a
Sunday; 500 free a month) saves every DK rung with the model's chance to `picks/rungs/`.
Audit F (`audit/shading.py`, Chris's idea): does DK charge more above the sharp no-vig price for
popular players' overs than for lesser players'? Needs no game results, only saved scans.
Until audit E shows the bet rule making money over 2-3 weeks, pregame prop edges are NOT backed.

Graded against the CLOSING line (what you actually bet), out of sample. Scripts: `audit/`.

| Bet | 2015-22 | 2023-26 | 2025-26 | Needs | Verdict |
|---|---|---|---|---|---|
| Teaser leg, NFL dog +1 to +2.5 (+6) | 74.9% | **79.3%** | ~77% | 73.9% (2-team -120) | **BACKED - best bet** |
| Teaser leg, NFL fav -7.5 to -8.5 | 77.4% | 62.3% | 64% | 73.9% | dead - do not use |
| Model LEAN+STRONG spread, vs close | 54.0% | **55.9%** | 55.7% | 52.4% | backed, small edge |
| Model STRONG only, vs close | 54.1% | 51.9% | 43.9% | 52.4% | no better than LEAN - merged |
| Prop yardage ladders, model 70-75% | | hit 76.2% | | DK implied | calibrated overall, but **UNPROVEN vs DK prices** (live: pregame legs 5-6 when the model said 67%). Not backed until audit E shows a profit |
| College spreads/totals (live 2026) | | | 30-41 | | fun only |
| **College model vs CLOSING lines, out of sample 2019-26 (Nov 14)** | | spreads 48.2% (6,451), totals 47.5-49.9% (unders 48.3%) | | 52.4% | **NO SKILL - worse than a coin flip** |

- Expect less than the table: many variables were tried, which flatters backtests.
- Prop prices: `run.py props --line "Name:receiving_yards=40+@-250"` prints the edge vs DK.
- Every recommended combo is logged and graded in `picks/recs.csv` with `recs.py`.
- **Miss review (Nov 15)**: losing NFL spread bets lose by 10.1 pts on average (any bet); the model's
  losses average 8.9. Weak spots cut from LEAN/STRONG: 0-3 pt favorites (48.0%, 100) and 7.5-10 pt dogs
  (51.6%, 64). After: 57.8% (2015-22) / 59.7% (2023-26) vs the opener (cuts chosen on this data).
  LEAN/STRONG dog picks +1..+3 teased 6 won 79.4% (262): the card prints MODEL DOG + TEASER.
- **BET EARLY (Nov 15)**: the NFL model's edge is mostly against the OPENING number (LEAN+STRONG
  56.7% 2015-22, 57.1% 2023-26; vs close 51.8% / 55.6%). `run.py early` prices the week vs DraftKings'
  current line as soon as it is posted. College does not work this way (about 50% vs open too).
- **Rebuild test (Nov 14, `audit/market_error_model.py nfl|cfb`)**: a model of the CLOSING line's
  mistakes from situations only (no team strength), walk-forward. NFL spreads/totals and college
  spreads: no edge (47-54%). College totals when the model says 56%+: 55.6% (2018-22, 656) and
  53.4% (2023-26, 481) - best of 32 settings tried, so partly luck. Old NFL model re-tested vs close:
  STRONG 54.8% (2015-22) / 55.6% (2023-26); LEAN+STRONG 51.8% / 55.6% (weaker than claimed before).
- **Rule scan (Nov 14, `audit/rule_scan.py`)**: 966 simple NFL rules x bets vs the CLOSING line,
  found on 2009-17, validated 2018-22, confirmed 2023-26. 16 passed find+validate, 5 also 2023-26.
  Most consistent: HOME QB CHANGE -> UNDER (56.5% / 59.2% / 54.5%, 457 games) and DIVISION GAME
  wk1-4 -> DOG ATS (60.1% / 55.4% / 54.1%, 344). Several 'team lost by 14+ last week -> under'
  rules won 56-64% for years then lost in 2023-26 (edges fade). 966 tries means some survivors are luck.
- **Why picks missed (Nov 10 review of every logged pregame leg vs DK's price at the time):**
  legs where the model was 6+ points above DK went 0-5 (Swift, Jones, Gainwell - role/committee
  news the model cannot see); legs within 6 points of DK went 5-7. So a big model-over-DK gap is
  treated as missing information: the scan marks it SKIP (`MAX_MODEL_GAP`). Also one leg per
  player per day (`recs.py add` refuses a second), since one bad game sank 4 Swift legs. Small
  sample (12 legs): audit E's edge buckets will confirm or move the 6-point cutoff.
- **No guessing (Chris, Nov 10).** Every chance, price or dollar figure quoted must come from a
  tool's output or a tested result, named as such; otherwise say "I don't know".
- **No gut overrides (Chris, Nov 8).** Picks come from the tools' output only. Do not drop or
  downgrade a model leg because it "disagrees with the market" or "looks off"; the model's 3%+
  ladder edges are the audited bet (hit 76% at 70-75%). Only skip a leg for a failed check
  (player inactive / QB change / NOT VERIFIED item), and say which check.
- **Ladder scanner**: `run.py props --week N --team X --team Y --scan Bears` prices every DK rung:
  `model` (audited), `sharp` (sharp main line stretched to the rung with the model's outcome
  shape; untested, no prop-odds archive), BOTH = both beat DK by 3%+. Rank: BOTH > model only > sharp only.
- **Live (in-game) ladders**: `run.py live --team CHI --odds-team Bears` = DK live rungs vs the
  in-game model (`nflmodel/live.py`: stats so far, score margin, time left + pregame averages;
  play-by-play cut every 7.5 min, 2018+). Audit `audit/live_audit.py` (train 2018-22, test 2023-26):
  calibrated within 1 point through the 3rd quarter (said 55% hit 54%, 85% hit 85%); 4th quarter ran
  3-4 points high, so 3.5 points are taken off there. Bet rungs 3%+ over DK, at or better than shown.
- **Bet shape (Nov 8)**: parlays multiply misses (two 72% legs win 52%, three win 37%). Default
  to SINGLES on legs the model puts at 70%+ with a 3%+ edge (the audited 76% hit rate), 2-leg max
  for parlays, teaser legs on NFL dogs +1 to +2.5, and live rungs at halftime (`run.py live`).
  3+ leg parlays only with a boost, and only legs that each have an edge.
- **Boosts**: `run.py parlay --leg "72%@-134" --leg "68%@-217" --boost 30` = chance and expected
  return; a DK profit boost often turns a fair parlay into a winning one. Use boosts on legs with edges.
- **Markets the user's DraftKings account does not offer**: receptions, rush attempts, and any
  unders (props are "X+" over ladders only). Build prop legs from yards, TDs and passing only.
- **Live odds (The Odds API)**: `python run.py odds --team Bears` lists DraftKings legs with the sharp
  books' no-vig chance (Pinnacle first). Needs `ODDS_API_KEY` set in the environment's settings
  (the API takes the key in the URL, so the proxy cannot add it).
- **RB rushing game script (Nov 9)**: favored backs' ladders now come from favored backs' history
  and are not shrunk toward 50/50 (2023-26: model 72-73% vs actual 79-80% before; 77-78% after).



## V2 flaws found Nov 15 (checked with data, /tmp scripts reproduced in v2/)
1. Spread "55%" was the record vs the OPENING line. On game day the card compares to DK's current
   line, where the record is 52.6% (2015-22) / 49.5% (2023-26). Card labels fixed.
2. Teaser records were quoted for 2023-26 only. 2015-22: dog +1..+2.5 69.9% (below 73.9% needed).
3. Totals lean Over: 2026 model picked Over in 92% of games, 52% went Over (+1.36 pts bias).
4. Props card fed the model this-season-only history (games count ~6 vs ~52 in training, weighted
   averages different for 33-43% of players). Fixed: career history like training. After the fix,
   Tuten TD, Stroud 250+, Love 256+, Goff 3+ TD no longer beat DK.
5. Anytime TD: top-range chances have too few test cases, so stars (Gibbs) get no tested number.
6. Props are priced before game-day inactives (posted ~90 min before kickoff); re-run needs API credits.
7. ROLE CHECK flags any teammate who missed one of the last 3 games - also flags players who are on IR or cut.
8. Props vs DK prices still untested: audit/v2_vs_dk.py grades the Nov 15 saved prices (made by the
   card BEFORE fix 4).

## V2 fixes Nov 15 (second session) - `PYTHONPATH=. python v2/improve.py` reproduces the numbers
Records are walk-forward, 2015-22 / 2023-26, pick graded at the game-day line.
1. **Wind was missing.** games.csv has no wind for 46% of 2022 outdoor games, 21% of 2023 and every game
   since 2026 week 5; the totals model read that as 0 mph and picked Over in 100% of 2026 games from
   week 5 on. Now filled from the play-by-play weather text, then the kickoff forecast, else the outdoor
   average (8.3 mph). 2026 Over picks: 92% -> 70%.
2. **The ridge ignored most play-by-play stats.** Features were not put on one scale, so the rate stats
   (EPA/play, success rate, pressure) were shrunk to almost nothing. Now standardized; ridge strength 10,
   picked on 2015-22 only.
3. **The card fit the spread model on the opening line but picked against DK's game-day line.** Now fit
   on the game-day line. Before (old card method): edge 1+ 52.7% / 49.0%. After: 52.8% of 849 / 55.0% of 311;
   edge 2+ 57.0% of 214 / 58.1% of 62. All games 52.4% / 50.7%. Break-even is 52.4%: the samples are too
   small to call this a proven edge.
4. Totals after the fixes: all games 53.2% / 51.7%, edge 1+ 55.8% / 50.8%. No edge in 2023-26. Removing the
   Over lean with a trailing average was tested and did not raise the win rate, so it is not used.
5. Teaser legs re-tested: dog +1..+2.5 69.7% / 77.9%, +3..+3.5 76.9% / 70.4%, favorite -3.5..-7.5 teased
   70.0% / 74.6%. None clears 73.9% in both periods.
6. Bugs: a game with no starter listed yet (weeks 12+) counted as a QB change; test_nfl.py crashed on
   totals vs the opener (no opening totals before 2024); the card priced games already in progress against
   DK's live line (now skipped).
7. Still open: the card's QB names come from nflverse and can be stale (Nov 15: it listed Darnold for SEA
   while ESPN had him Out). props_card.py's alt spreads still fit on the opener and its calibration was
   not re-run after fix 2.

## Dig for a game-day edge (Nov 15, `PYTHONPATH=. python v2/dig.py`)
Five ideas fixed before looking, graded at the closing line, 1999-2014 / 2015-22 / 2023-26.
1. **Teaser leg on EVERY dog +1.5 to +2.5 (6 points, no model): 72.7% of 395 / 77.0% of 283 / 77.3% of 207.**
   With the game total 44 or less: 75.9% of 278 / 77.4% of 115 / 78.9% of 109 - above the 73.9% a 2-team
   -120 teaser needs in all three periods. Total over 44: 65.0% / 76.8% / 75.5%. Actual same-week 2-team
   teasers of these dogs won 55.0% / 60.6% / 63.8% (break-even 54.5% at -120, 56.5% at -130, 58.3% at -140).
   The v2 model's dog picks did worse than all dogs (69.7% in 2015-22), so the model is NOT used to pick legs.
   DK's teaser price was not checked - read it on the bet slip.
2. Dog +3: 72.7% / 75.0% / 66.7%. Dog +3.5..+6.5: 67.7% / 73.9% / 67.9%. Favorite -7.5..-8.5: 72.7% / 76.8% / 63.2%. No.
3. Moneylines at closing prices: no price range made money in both 2015-22 and 2023-26.
4. Fading lines that stray from the market's own team ratings: 51-55% / 49-52% / 42-49%. No.
5. nfelo's line vs the close: 53-57% / 56-58% / 47-51%. Worked for years, not since 2023. No.

## Three gaps tested (Nov 23, `PYTHONPATH=. python v2/test_three.py`)
Chris asked whether the model accounts for pass rush, pressure and special teams. It already used team
pressure ((sacks + QB hits) per dropback, line allowed and defense made) and one special-teams number
(EPA on all kicking plays). Removing pressure cut spread all-games from 52.4% / 50.7% to 51.5% / 50.1%;
removing special teams cut it to 50.8% / 50.5%. Then three missing pieces were tested
(walk-forward, graded at the game-day line, 2015-22 / 2023-26; switches in v2/nfl.py, all OFF):

| Version | Spread all | Spread edge 1+ | Total all | Total edge 1+ |
|---|---|---|---|---|
| Baseline (card) | 52.4% / 50.8% | 52.8% / 54.1% | 53.2% / 50.5% | 55.8% / 50.6% |
| A. Opponent-adjusted, half | 52.1% / 50.2% | 54.4% / 52.8% | 53.5% / 50.4% | 55.1% / 50.2% |
| A. Opponent-adjusted, full | 52.9% / 50.5% | 54.1% / 50.4% | 54.2% / 50.2% | 55.1% / 50.0% |
| B. Pass rushers Out/Doubtful | 52.0% / 50.8% | 53.4% / 53.4% | 53.5% / 51.0% | 56.0% / 51.4% |
| C. ST split, replaces ST number | 51.9% / 49.6% | 54.4% / 53.6% | 54.2% / 49.6% | 54.9% / 48.1% |
| C. ST split, added | 52.2% / 51.6% | 54.2% / 53.4% | 54.0% / 48.7% | 54.6% / 49.5% |
| A + B + C together | 54.0% / 49.1% | 54.4% / 52.4% | 53.1% / 49.2% | 55.6% / 47.5% |

- A (opponent adjustment) and C (special teams by unit: FG, punting, punt return, kick return, kick
  coverage) help 2015-22 and hurt 2023-26. Together they reach 54.0% in 2015-22 and fall to 49.1% in
  2023-26: fitting the past, not predicting.
- B (share of a defense's last-8-game sacks + QB hits made by players listed Out/Doubtful) is the only
  one that raised totals in both periods, by 0.3-0.8 points, still below break-even in 2023-26. Spreads mixed.
- B added to TOTALS only (Chris, Nov 23; `RUSH_OUT_TOTAL` in v2/nfl.py). A and C not adopted. Data: v2/extra_data.py (nflverse player stats + injury reports; play-by-play by unit).

## Four more inputs tested (Nov 23, `PYTHONPATH=. python v2/test_four.py`)
Same test (walk-forward, game-day line, 2015-22 / 2023-26), starting from the card as it was.

| Version | Spread all | Spread edge 1+ | Total all | Total edge 1+ |
|---|---|---|---|---|
| Baseline | 52.4% / 50.8% | 52.8% / 54.1% | 53.5% / 51.0% | 56.0% / 51.4% |
| 1. Starting QB's own value | 52.7% / 51.8% | 54.2% / 53.3% | 52.6% / 50.1% | 55.9% / 50.8% |
| 2. Referee crew (totals) | same | same | 53.3% / 50.9% | 55.9% / 51.2% |
| 3. Pace and pass rate | 52.3% / 49.2% | 52.4% / 50.0% | 53.3% / 51.1% | 54.3% / 50.4% |
| 4. Red-zone TD rate | 52.1% / 50.8% | 54.6% / 57.3% | 52.6% / 51.1% | 55.5% / 51.2% |
| **1 + 4 (ADOPTED for spreads)** | **52.4% / 52.0%** | **54.9% of 1002 / 54.9% of 388** | 52.6% / 50.4% | 55.3% / 50.9% |
| 1 + 2 + 3 + 4 | 52.6% / 49.9% | 55.3% / 53.3% | 53.3% / 51.3% | 54.4% / 49.8% |

- QB value: the listed starter's career EPA per play (dropbacks + carries, any team), recent games weighted
  more (half-life 20 games), shrunk 200 plays toward what new QBs produced before 2015 (-0.062).
  So a backup now counts as a backup, not just "QB changed".
- Spread with 1 + 4, edge 2+: 57.8% of 306 / 55.9% of 111. Edge 1+ by season 2023-26: 55%, 58%, 53%, 55%.
  The combination was the 8th spread variant tried today, so some of the gain may be luck.
- Totals keep the old inputs (1 and 4 lowered totals). Referee: no gain, and games.csv only posts the
  referee after the game, so it could not be used before kickoff anyway. Pace: hurt spreads.
- Model teaser legs after the change: dog +1..+2.5 74.1% / 82.6%, +3..+3.5 77.3% / 70.7%,
  favorite -3.5..-7.5 69.7% / 73.6% (v2/test_teaser.py).
- Caveat: the QB value uses the schedule's listed starter. When the schedule is stale (Nov 15: Minshew,
  Huntley), the value is wrong too - the card's ** CHANGE QB lines matter more now.

## Backup RBs, WRs, TEs (Nov 23, `PYTHONPATH=. python v2/test_skill.py`)
Input: share of a team's last-8-game rushing + receiving yards (RB/WR/TE) made by players listed Out or
Doubtful that week, i.e. how much of the offense backups must replace. 20%+ in 495 of 4,902 games.
Walk-forward, game-day line, 2015-22 / 2023-26, from the current card (QB value + red-zone in spreads):

| Version | Spread all | Spread edge 1+ | Total all | Total edge 1+ |
|---|---|---|---|---|
| Current card | 52.4% / 52.0% | 54.9% / 54.9% | 53.5% / 51.0% | 56.0% / 51.4% |
| One number (RB+WR+TE) | 52.9% / 51.4% | 55.1% / 54.6% | 53.7% / 51.3% | 56.1% / 51.2% |
| RB, WR, TE separately | 53.5% / 51.2% | 54.8% / 54.3% | 53.4% / 51.4% | 55.5% / 50.8% |

Spreads: better 2015-22, worse 2023-26. Totals: +0.2-0.3 on all games, edge 1+ mixed. Not adopted
(`SKILL_OUT` in v2/nfl.py, off). The card still shows skill players out per ESPN as ** CHANGE lines.

## Depth check: top WRs/RB/TE out (Nov 23, `PYTHONPATH=. python v2/test_depth.py`)
Per team-game, 2012-22 / 2023-26: top-2 WRs, top RB, top TE (by yards, last 8 games) listed Out/Doubtful.
- One top-2 WR out (442 / 178 games): neutral pass rate -0.8 / -0.2 points vs the team's own average (no real
  shift to the run); line moved 0.44 / 0.31 pts against the team from open to close; team covered **45.1% / 46.9%**.
  Betting against it would have won 54.9% / 53.1% - found after looking at 6 groups, so not proven.
- Both top-2 WRs out: only 8 / 12 games - too few to say anything.
- Top RB out: covered 50.9% / 57.6%. Top TE out: 50.8% / 48.9%. Lines moved against the team in most groups.
- The v2 props model has NO vacated-targets input (only the ROLE CHECK flag). Untested gap.

## Props: freed-up targets/carries and "one big game" (Nov 23, `PYTHONPATH=. python v2/test_props_new.py`)
Fit 2015-22, scored on 2023-26. "Real minus model" = actual hit rate minus the model's chance (0 = right).

| Group (2023-26) | Market | Before | With freed-up targets/carries |
|---|---|---|---|
| A teammate at his position Out/Doubtful (4+ targets or carries freed) | receiving yards (11,154 rungs) | +2.7% | +0.5% |
| | receptions | +3.0% | +0.1% |
| | rushing yards (9,966) | +1.7% | +0.5% |
| | anytime TD (1,859) | +3.2% | +1.8% |

- The model used to UNDER-rate players who inherit a teammate's work; that is now mostly fixed. Brier
  score improved in every market but passing yards (slightly worse there, so passing yards skips it).
- Card: `[FREED UP: N targets / N carries ...]` on such legs; ROLE CHECK is unchanged.
- Chris's worry (Nov 23): "4 TDs in one game then 0, 0, 0 is not 1 TD a game". The chance is not an
  average: it is how often past players with similar inputs actually reached the number. Checked on
  players with a 2+ TD game in their last 8: yards markets real minus model -0.3% to +0.4% (no skew);
  anytime TD +2.8% (the model is slightly LOW on them, not high). Adding last-8 medians and the share of
  games with a TD (`USE_ROBUST`) did not improve anything, so it is off.

## Other ways to pick, not averages (Nov 23, `v2/test_methods.py`, `v2/test_methods_props.py`)
Game model, walk-forward, game-day line, 2015-22 / 2023-26 ("confident" = edge 1+ pts, or chance 53%+):

| Method | Spread all | Spread confident | Total all | Total confident |
|---|---|---|---|---|
| 0 Current (weighted averages, ridge on margin) | 52.4% / 52.0% | 54.9% / 54.9% | 53.5% / 51.0% | 56.0% / 51.4% |
| 1 Median of last 8 games | 51.5% / 52.9% | 52.5% / 52.8% | 52.8% / 49.8% | 54.2% / 52.0% |
| 2 Competitive plays only (win prob 10-90%), EPA capped +/-3 | 52.6% / 54.4% | 55.0% / 53.1% | 53.6% / 50.7% | 55.3% / 51.3% |
| 3 Blowouts capped at 14 pts in the fit | 52.2% / 51.5% | 55.7% of 578 / 55.8% of 217 | 52.9% / 51.1% | 54.9% / 49.5% |
| 4 Chance to cover (logistic, no margins) | 51.3% / 51.4% | 52.1% / 51.8% | 53.0% / 50.3% | 54.5% / 48.5% |
| 5 200 most similar past games | 50.3% / 47.6% | 53.5% / 49.2% | 49.1% / 47.2% | 51.3% / 46.7% |

Only 2 beat the current spread pick on all games in both periods (+0.2 / +2.4), but its confident
picks fell in 2023-26 (53.1% vs 54.9%). Chris chose it (Nov 23): ON for spreads (c_epa/c_sr/c_explosive replace the
all-play versions; `SPREAD_SKIP` in v2/nfl.py). Totals keep the all-play versions. Model teaser legs after:
dog +1..+2.5 73.2% / 82.7%, +3..+3.5 77.9% / 71.2%, favorite -3.5..-7.5 69.4% / 76.4%.

Props (fit 2015-22, scored 2023-26): the model had the best Brier score in all 7 markets. The player's own
hit rate ("60+ in 9 of his last 16") was worse everywhere and badly off at the top: passing yards said
73% and hit 68%; rushing yards said 71% and hit 79%. Half model / half own rate was in between.

## Receptions flaw fixed (Nov 23, `PYTHONPATH=. python v2/test_receptions.py`)
Receptions chances came from 25 wide groups of projections; the top group mixed 5- and 9-catch
projections, so high-volume receivers (recent average 7.5+ catches) were under-rated: every rung said
65.9%, hit 72.3%; 8+ said 28.6%, hit 37.6% (133 games, 2023-26). Now the chance comes from the 500
past players with the closest projections (`NEAR` in v2/props.py): 70.2% vs 72.3%, 8+ 33.6% vs 37.6%;
Brier 0.0825 -> 0.0824, calibration elsewhere unchanged. Tried and rejected: projection + misses (like
yards) - Brier 0.0844, chances 7-9 points too low in the middle. Same fix for passing TDs: no change, not used.
