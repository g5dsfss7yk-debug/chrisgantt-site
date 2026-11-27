# v9 weather severity - results (rules: v9/PROTOCOL.md, committed first at 12067d4)

Data: Open-Meteo hourly history at each stadium, kickoff + 3 hours, 3,896 of 4,101 outdoor games 2006-26
(205 not located or not fetched). Games: rain 0.10+ in 204; heavy rain 0.30+ in 44; cold+wet 17; gusts 30+ 333; snow 9.

## Passed
| Test | 2006-16 / 2019-22 | 2017-26 / 2023-26 | vs plain "bad weather" |
|---|---|---|---|
| S4 total UNDER, gusts 30+ | 93/168 = 55.4% | 96/162 = 59.3% | bad weather: 55.6% / 59.9% |
| S6 receiving yds UNDER, heavy rain | 65.9% vs model 58.8% (+7.1) | 68.9% vs 58.2% (+10.7) | bad: +5.3 / +6.7 -> heavier is worse |
| S7 receptions UNDER, heavy rain | 59.3% vs 54.9% (+4.5) | 65.1% vs 54.9% (+10.2) | bad: +2.8 / +6.5 -> passes only when heavy |
| S11 passing yds UNDER, gusts 30+ | 65.8% vs 51.1% (+14.7) | 63.0% vs 46.9% (+16.1) | bad: +13.6 / +18.3 |

## Failed / could not be tested
- Rain 0.10+ total Under: 60.2% / 58.6% but 98 and 99 games (rule needs 100 each) - FAIL on count, close.
- Heavy rain total Under 66.7% / 57.1% (15 / 28 games); heavy rain passing Under +14.1 / +16.0 (24 / 27 players): too few.
- Snow (9 games) and cold+wet (17 games): far too few to test.
- **Rushing yards OVER in heavy rain: went the OTHER way** (-3.6 / -9.3): teams may run more, but running backs fell
  short of their projections too. Found after the fact - not a pick.

## Limits
Tested on actual weather; the card uses the forecast. Props tested vs the v3 projection, not DK's price.
