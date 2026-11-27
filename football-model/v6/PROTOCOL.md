# v6 weather test - written and committed BEFORE any v6 result was computed (Nov 26 2026, ~6:20 PM CT)

Chris (Nov 26): "If it's raining hard, less likely to throw and more run offense." v3 left weather out because the
schedule's wind/temp columns are missing for every outdoor 2026 game after week 4 (v3/results/data_audit.txt) and it
has no rain field. This tests weather as an ADD-ON flag; the frozen v3 model is not changed or refit.

## Data
- Weather = nflverse play-by-play `weather` text (NFL game-book conditions at kickoff, e.g. "Rain Temp: 53 F,
  Humidity: 79%, Wind: SW 9 mph"). Present for every outdoor game checked (2012, 2022, 2026). Open-Meteo's history API
  is blocked in this container, so no other source is used.
- Games: outdoor or open roof only (nflverse `roof` in outdoors/open). Domes and closed roofs are left out.
- CAVEAT: this is the weather AT KICKOFF. On game day the card only has ESPN's forecast. A pass means "this works
  when the forecast is right"; forecast misses are not tested.

## Definitions (fixed now)
- WET: lower-cased text matches `\b(rain|raining|showers?|drizzle|snow|snowing|sleet|thunderstorms?|storms?)\b`
  and does NOT match `\b(no (rain|snow)|chance|possible|possibly|ending|ended|stopped|earlier)\b`.
- WINDY: sustained wind (first number after "Wind") >= 15 mph, or "Gusts to N" with N >= 25.
- BAD = WET or WINDY. GOOD = outdoor games that are neither (printed as a control, no pass/fail).

## Tests (6, all fixed now; nothing else is tried)
Game totals - bet the UNDER at nflverse's closing total, graded at -110 (break-even 52.4%), pushes thrown out:
- G1 WET games, G2 WINDY games, G3 BAD games.
- EARLY 2006-2016, LATE 2017-2026 (games played so far).
Props - in BAD games, line = the v3 projection rounded to x.5 (props.half), compare the actual hit rate with the v3
Pricer's predicted chance for that side:
- P1 passing yards UNDER, P2 rushing yards OVER, P3 receiving yards UNDER.
- EARLY: Pricer trained 2013-18, scored 2019-22. LATE: trained 2013-22, scored 2023-26 (as PROTOCOL amendment 4).
  Players need 3+ prior qualifying games (same rows the v3 props test used).

## Pass rule
- Totals (same as v3): EARLY >= 52.4%, LATE >= 52.4%, EARLY+LATE beats 50% with one-sided binomial p < 0.05,
  100+ bets in EACH period. Fewer than 100 in a period = FAIL (too few).
- Props: actual hit rate minus mean predicted chance >= +3.0 points in BOTH periods, 100+ player-games in each,
  and EARLY+LATE combined one-sided binomial p < 0.05 against the mean predicted chance. Note: no DK prop prices
  exist for history, so a pass shows the v3 projection misses weather - NOT that DK's prices miss it.

## If something passes
Card/props print it as a weather flag next to the forecast: e.g. "WEATHER (v6 G3): Under, tested X% / Y%" for
totals, and "WEATHER (v6 P1): projection runs high in bad weather" on the prop line. Label TESTED PICK (totals) or
NOT VERIFIED -> adjust note (props). Live record judged by v3/scoreboard.py. Anything that fails stays a plain flag
(as now). Results go in v6/RESULTS.md; this file is not edited after results exist (Amendments section only).

## Amendments
1. (Nov 26, BEFORE any result was computed - only counts and sample texts looked at.) Parser bug: "first number after
   Wind" picked up the temperature in texts like "windy with strong gusts ... Temp: 16". Now the first number inside
   the "Wind:" field (up to 25 non-digit characters after "Wind:"). WET 297 games, WINDY 484, wind parsed 98%.
2. (Nov 26, AFTER results.) Card hook-up - not tested: ESPN gives a forecast (gusts, rain chance), not the game-book
   text. Forecast mapped to the tested conditions as: WINDY = gusts 25+ (the test's gust rule; no sustained wind in
   ESPN's forecast) -> G2; else rain chance 50%+ -> G3 (BAD). Card prints ">> WEATHER UNDER" as TESTED PICK unless DK's
   Under juice needs more than the lower tested rate (then NOT A BET (price)). Props print the P1/P3 result as a
   weather note; the v3 chances are not changed (frozen). Market 'weather_under' graded like a total.
