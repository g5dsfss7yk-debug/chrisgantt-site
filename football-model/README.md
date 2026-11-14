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

- Expect less than the table: many variables were tried, which flatters backtests.
- Prop prices: `run.py props --line "Name:receiving_yards=40+@-250"` prints the edge vs DK.
- Every recommended combo is logged and graded in `picks/recs.csv` with `recs.py`.
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

