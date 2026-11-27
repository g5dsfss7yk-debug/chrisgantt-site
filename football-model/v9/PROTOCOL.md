# v9 weather SEVERITY test - written and committed BEFORE any v9 result was computed (Nov 26 2026, ~8:20 PM CT)

Chris (Nov 26, KC@BUF in a freezing downpour): "I think you generalized the weather." v6 is yes/no (any rain, or
wind). This tests whether HOW MUCH rain / how cold / how windy matters. Add-on only; v3 and v8 are not refit.

## Data
- Open-Meteo historical weather (archive-api.open-meteo.com; Chris approved the host Nov 26), hourly precipitation
  (inches), temperature (F), wind gusts (mph) at the stadium's city (ESPN venue city/state -> Open-Meteo geocoding).
- Game window = kickoff hour (nflverse gameday + gametime, US Eastern) and the next 3 hours (4 hours).
  rain = total precipitation in the window; temp = mean temperature; gust = max gust.
- Outdoor/open-roof games only, 2006-2026. Games whose stadium cannot be located are left out (count reported).

## Levels (fixed now)
- WET1: rain >= 0.10 in. HEAVY: rain >= 0.30 in. COLDWET: rain >= 0.10 in and temp <= 36 F. GUST30: gust >= 30 mph.

## Tests (12; nothing else is tried)
Totals - UNDER at nflverse's closing total, -110 (needs 52.4%), pushes out. EARLY 2006-16, LATE 2017-26.
Pass = both periods >= 52.4%, combined one-sided binomial p < 0.05, 100+ games each period (fewer = FAIL).
- S1 WET1, S2 HEAVY, S3 COLDWET, S4 GUST30.
Props - v6 method: line = v3 projection rounded to x.5, actual vs v3 Pricer chance for that side. EARLY: Pricer
2013-18 scored 2019-22; LATE: Pricer 2013-22 scored 2023-26. Pass = +3.0 pts both periods, 100+ each, p < 0.05.
- S5 passing yds UNDER in HEAVY; S6 receiving yds UNDER in HEAVY; S7 receptions UNDER in HEAVY;
  S8 rushing yds OVER in HEAVY (Chris: "running the hell out of the ball").
- S9 passing yds UNDER in COLDWET; S10 receptions UNDER in COLDWET.
- S11 passing yds UNDER in GUST30; S12 receptions UNDER in GUST30.
Severity vs v6: every result is printed next to the same test on ALL v6-BAD games, so it shows whether the heavier
level is worse than the plain yes/no flag (information; the pass rule above decides).

## If something passes
Card/props: live amounts from Open-Meteo's hourly FORECAST (api.open-meteo.com) for the same 4-hour window. Totals
passes print ">> WEATHER (v9 <level>) UNDER" as TESTED PICK (NOT A BET above the lower tested rate); props passes
print a note with the tested numbers (v8 chances unchanged - v8 has only the yes/no weather input).
Results: v9/RESULTS.md. Forecast amounts vs actual amounts are not tested.

## Amendments
1. (Nov 26, before any result.) Season-long archive requests were refused by the service (HTTP 400 / connection
   resets); fetch now asks one stadium-day at a time (cached in data/v9/raw). Same data, same window. No result seen.
