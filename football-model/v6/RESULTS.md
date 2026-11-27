# v6 weather test - results (rules: v6/PROTOCOL.md, committed first at 6ee1040)

Run: `python v6/test_weather.py` -> v6/results/weather_test.txt. Weather = nflverse game-book text at kickoff,
outdoor/open-roof games 2006-2026: 4,101 games, WET 297, WINDY 484, BAD (either) 724.

## Totals - Under at the closing total, graded at -110 (needs 52.4%)
| Test | 2006-16 | 2017-26 | combined p | Result |
|---|---|---|---|---|
| G1 WET | 74/146 = 50.7% | 95/144 = 66.0% | 0.003 | FAIL (early below 52.4%) |
| G2 WINDY (15+ mph or gusts 25+) | 162/290 = 55.9% | 106/187 = 56.7% | 0.004 | **PASS** |
| G3 BAD (wet or windy) | 220/401 = 54.9% | 188/311 = 60.5% | <0.001 | **PASS** |
| control: good weather | 862/1774 = 48.6% | 785/1554 = 50.5% | 0.73 | (no bet) |

## Props in BAD games - line = v3 projection; actual vs model's predicted chance (needs +3 pts both periods)
| Test | 2019-22 | 2023-26 | Result |
|---|---|---|---|
| P1 passing yards UNDER | 63.9% vs 49.9% (+14.0), n=277 | 65.9% vs 47.9% (+18.0), n=211 | **PASS** |
| P2 rushing yards OVER (Chris's "more run") | 41.8% vs 40.8% (+0.9), n=938 | 39.8% vs 40.9% (-1.1), n=704 | FAIL - no effect |
| P3 receiving yards UNDER | 63.6% vs 58.3% (+5.3), n=2141 | 64.4% vs 58.1% (+6.3), n=1597 | **PASS** |
Good-weather control games: actual within ~1 pt of the model for all three.

## Limits
- Tested on weather AT KICKOFF; the card uses ESPN's forecast (amendment 2 mapping, not tested). Forecast misses lower the real rate.
- Props: no DK prices in history, so P1/P3 show the v3 projection runs high in bad weather, not that DK's prop prices miss it.
  The P1/P3 numbers are at a line equal to the projection; at other lines the size of the effect is not known.
- Totals were graded against nflverse's closing line, not DK's.
