# NFL game model

Predicts each NFL game's margin (the model's spread), win probability and total points,
using free public data from [nflverse](https://github.com/nflverse).

```
pip install -r requirements.txt
python run.py backtest          # walk-forward test, 2015-2025, vs Vegas lines
python run.py predict           # next unplayed week
python run.py predict --week 7 --weather BUF=28,18   # override forecast: tempF,windMPH
```

## Variables
| Group | Features |
|---|---|
| Team strength | Elo rating (margin-of-victory adjusted, regressed 1/3 each offseason), EWMA points for/against |
| Quarterback | QB value (shrunk average of results vs. expectation in his starts), career starts, backup-QB flag |
| Injuries | Official injury report, each player weighted by P(miss) (Out 1.0 / Doubtful 0.85 / Questionable 0.25) x position value x recent snap share; split into offense and defense |
| Weather | Temperature, wind, dome/retractable roof, turf, dome teams playing outdoors in the cold |
| Schedule/travel | Home field (off for neutral sites), rest days, byes, short weeks, travel miles, time zones crossed, West Coast teams in 1pm ET games, divisional games |

Training uses 2012+ (when injury and snap data both exist). Every feature is computed only
from information available before kickoff.

## Limitations
- No live weather forecast: future games use stadium/month climatology unless you pass `--weather`.
- Upcoming starting QBs come from nflverse's projected starters. Check for late QB changes.
- In backtests the model is roughly as accurate as Vegas but **not** better against the spread.
  See `python run.py backtest`.
