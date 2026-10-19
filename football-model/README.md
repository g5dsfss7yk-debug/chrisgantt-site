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
1. **Rating (stage 1).** Ridge regression from football features to the home margin and
   to the game total. It never sees a betting line.
2. **Edge (stage 2).** The market is usually right, so only part of the gap between the
   rating and the line is real. A logistic regression, fit on out-of-sample ratings from
   earlier seasons, turns that gap into the probability the bet wins. These are
   calibrated: picks the model gives 57% have won about 57-61%.
3. **Timing.** Spreads are judged against the **opening line** using only information
   known when lines open; lines tend to move toward the model during the week. Totals
   are judged on game day, when the forecast and final injury report are in.
4. **Card.** A bet is marked only when P(win) clears the cutoff chosen on 2015-2022
   (spreads 56%, totals 55%). Spread picks are held when the listed QB differs from last
   week's starter. A card is saved once and not changed; `grade` scores it.

Backtest at the cutoffs (`python run.py backtest`): spreads 187-119 (61.1%) in 2015-2022
and 54-38 (58.7%) in the untouched 2023-2026 holdout. Totals clear the cutoff only a few
times a season: the market's totals are hard to beat.

## Data
| Source | Used for |
|---|---|
| nflverse games | scores, closing lines, roof, surface, rest, QBs, coaches |
| nflverse play-by-play | opponent-adjusted EPA/play and success rate, turnovers, weather text (rain/snow/gusts) |
| nflverse injuries + snap counts | snap-weighted injury burden, roster continuity |
| nflverse weekly rosters | returning and added production |
| [nfelo](https://github.com/greerreNFL/nfelo) | opening spreads, independent Elo with QB adjustments |
| `nfl-weather` branch | kickoff forecasts, fetched every 3 hours by `.github/workflows/nfl-weather.yml` |

## Features
| Group | Known at open | Game day only |
|---|---|---|
| Strength | Elo, nfelo, points form, EPA and success rate, turnover and close-game luck | |
| Quarterback | QB value, experience, QB new to team | backup starting |
| Change | returning/added snaps, coach tenure, stale-rating fade | |
| Situation | home field, division, rest, byes, short weeks, travel, time zones | |
| Injuries | | final injury report |
| Weather (totals) | | temp, wind, gusts, rain, snow, dome, turf |
