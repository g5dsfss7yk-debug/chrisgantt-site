# HANDOFF - core model (Nov 28 2026). Read the repo-root CLAUDE.md first, then this.

Branch `claude/modest-galileo-zg0mve`. **Only `football-model/core/` makes picks.** Chris, Nov 28: "There should be
no old models picking anything." v2-v11, run.py and the old cards exit with a RETIRED message.

## Files
| File | What |
|---|---|
| `core/PROTOCOL.md` | Every rule, written BEFORE each result (amendments 1-19 so far) |
| `core/RESULTS.md` | Every result, passes and fails, with cautions |
| `core/data.py` | Downloads (cfbfastR, CFBD lines/talent/returning/venues, nflverse, ESPN) into `data/core/` |
| `core/cfb.py`, `core/nfl.py` | Game models (8 opponent-adjusted stats incl. defense, QB, Elo/talent/returning/rest/travel (college), injuries/starters/weather (NFL), the line) |
| `core/card_cfb.py EVENT_ID ...` | College card: every check it can do; logs `core/picks/log.csv` |
| `core/card_nfl.py` | NFL card (same idea; ESPN injuries, QB, inactives, weather, teaser legs) |
| `core/props_nfl.py` | NFL props test (every prop is a LEAN; DK beat it on 119 logged prices) |
| `core/picks/log.csv`, `core/picks/bets.csv` | Card picks / Chris's PLACED bets (real stake, DK slip) |

First run in a new container: `pip install pandas numpy pyarrow scikit-learn scipy`, then
`python football-model/core/data.py cfb 2014 2026` and `python football-model/core/data.py nfl 2006 2026` (a few minutes).

## Tested picks (core) - judged by the live record
- College spread 2+ pts off the DK line (in-season recalibrated): 56.3% / 54.7%.
- College total 2+ pts off the DK line (last-3-season median model): 53.1% / 57.2%.
- NFL 6-pt teaser leg on every dog +1.5..+2.5: 76.5% / 77.1% (needs 73.9% per leg at -120).
Everything else is a LEAN with its record. Many tests were run - luck is possible.

## Chris's choices / lessons
- Wants a pick on every game; do not say "no bet" - label it and skip only failed checks.
- Dislikes Unders (old models picked them and they lost): NFL totals stay on the original (Over-leaning) model.
- Thinks old seasons matter less (league changes): the recent-only fit worked for college totals; NFL got worse.
- Game-day observations (QB news, weather) are a check - he was right on KC@BUF weather and Texas A&M's two QBs.
- College has NO injury/lineup data: every college pick says so; Chris checks the starting QB.

## Live record
Nov 27 college card: spreads 1-1, winners 2-0, totals 0-2 (old Over-leaning college totals; now median).
Chris's bets: MIN@WIS teaser Wis -2.5 / Over 30.5, $5 at -115, WON $9.34.

## Open
- Scheduled tasks: "NFL game-day picks - Thu/Mon night" DISABLED Nov 28. "NFL game-day picks - Sunday" still
  ENABLED and points at the retired v5/gameday.py (disabling was blocked by the session's permission check) -
  it will only print RETIRED until Chris disables it or approves repointing it to core/card_nfl.py.
- B (sharp-price comparison): needs env var ODDS_API_KEY in the cloud environment settings (credits were 0 Nov 26).
- Ideas not yet tried: log Chris's game-day reads next to picks; drive-by-drive simulation for totals.
- cfbfastR 2026 play-by-play lags (ended at week 12 on Nov 27) - the card prints the last week it has.
- Open-Meteo is rate-limited some days; v9 Miami weather re-fetch is moot (v9 retired).
