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
   Totals are bet only in outdoor games with 15+ mph wind or rain/snow (Under); heavy
   defensive injuries are flagged as an Over to watch. A card is saved once and not
   changed; `grade` scores it.

Backtest against opening lines (`python run.py backtest`):

| Tier | 2015-2022 | 2023-2026 (held out) |
|---|---|---|
| STRONG | 147-88 (62.6%) | 69-54 (56.1%) |
| LEAN | 329-239 (57.9%) | 177-131 (57.5%) |

Model totals lost in 2023-2026 with every learner and feature set tried, so they are shown
for information only. Weather Unders went about 55% in both periods.

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
(totals now centered on the model's recent gap to the line) the edge is gone. Totals of 65+
are flagged as an Under to watch: 55-56% through 2023, below 52% since.
