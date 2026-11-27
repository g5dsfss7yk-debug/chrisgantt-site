# v11 ONE combined game model - results (rules: v11/PROTOCOL.md + amendment 1, committed first)

`python v11/model.py test`. One model: v3 game features + weather severity (Open-Meteo hourly) + backup QB + key
receiver / lead RB out + defensive starters out + team yardage from the props projections. Fit from 2013,
walk-forward, compared with v3 on the SAME 3,287 games.

| Bet (all at -110, needs 52.4%) | v11 2014-18 | v11 2019-26 | v3 2014-18 | v3 2019-26 |
|---|---|---|---|---|
| spread, every game | 52.5% of 1146 | 50.8% of 2057 | 51.6% | 50.1% |
| total, every game | 49.6% of 1172 | 52.6% of 2087 | 48.1% | 51.4% |
| total, edge 1+ | 50.4% of 691 | 53.0% of 1134 | 47.0% of 511 | 50.6% of 618 |

- v11 beat v3 on every-game spreads AND totals in BOTH periods -> v11 now drives the card's spread/winner/total.
- No v11 bet type passed the TESTED PICK rule: still LEANs (better coin flips, not proven winners).
- What it learned (fit 2013-25): rain -7.3 total points per inch in the game window; -0.14 per mph of gusts over 15;
  each backup QB in the game -0.6 total points; each lead RB out -1.4. Most other new inputs were small.
- Tested picks that stay as they are: teaser legs, price gap, v6/v9 weather Unders. Props: v8 (same inputs).

Live: `v3/card.py nfl --week N` prints the v11 numbers, its inputs, and v3's numbers beside them. Weather inputs come
from Open-Meteo's forecast; if it is unavailable the card says so and weather counts as 0.
