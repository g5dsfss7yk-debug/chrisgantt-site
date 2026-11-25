# Brief for a NEW football betting model (written Nov 24 2026)

Chris wants a fresh build. Do NOT reuse or patch the old code (`nflmodel/`, `v2/`, `cfbmodel/`);
read it only to see what was tried. This brief is what the last build learned the hard way.

## Who Chris is and what he wants
- Bets **$2 per pick on DraftKings**, NFL and college. Wants to **win**, not to hear "no bet".
- Wants a **pick (a lean) on every game**: spread, winner, total - each clearly labeled
  TESTED PICK (has a passing test record) or LEAN (no proven edge).
- Wants props, including **unders**: unders happen; they just have to be priced correctly.
  (Note: in the past his DK prop ladders showed only "X+" overs - check what his DK offers.)
- Does **not bet early in the week** (injuries/lineup changes). Picks are made on game day, against
  DK's game-day number. Never quote opening-line records as if they apply to him.
- Wants plain, short answers. No fluff, no excuses, no lectures.

## The honest record of the last build (pick log `picks/recs.csv`)
| | Record |
|---|---|
| Every recommendation | 77-112 (41%) |
| Old models (before Nov 15) | 63-97 (39%) |
| Rebuilt models since Nov 15 | 14-15 (48%); singles 12-11, parlays/teasers 2-4 |
| Bets Chris placed | 3-13 (19%) |
Backtests said 53-56%. Real results were far worse. Do not trust a backtest until new games confirm it.

## What went wrong (do not repeat)
1. **Patching after every loss.** One bad night is noise; each reaction made it worse.
2. **Testing ~30 changes against the same seasons.** Some "gains" were luck. The holdout stopped
   being a holdout.
3. **Overriding the model by hand** ("both defenses are bad, take the Over") and **giving picks from a
   model that had failed its test** (old college spread model: 48.2% vs close). Both lost money.
4. **Presenting small backtest edges with confidence.** 54% still loses 46 of 100.
5. **Parlays.** Misses multiply; 2-4 on the rebuilt models.
6. **Data bugs that went unnoticed for weeks:** schedule file missing wind for every 2026 game after
   week 5 (model read it as 0 mph and picked Overs); schedule's listed QB often stale (ESPN had the
   starter Out); features on different scales so the ridge ignored them; model fit on the opener but
   picked against the game-day line.

## Rules for the new build (set these BEFORE looking at any result)
1. Write the pass/fail rule first (e.g. "beats 52.4% at the game-day line in BOTH periods").
2. Choose every setting on the early period only. Check the later period ONCE. If it fails, it fails.
3. **Freeze** the model once it passes. Judge it only on games it has never seen (forward record).
   No changes mid-season except proven bugs.
4. Keep a **scoreboard** from day one: live record by bet type next to the tested record.
5. The model's output is the pick. No hand overrides. Skip only for a failed check (QB out, inactive).
6. Grade against the price Chris actually gets (DK game-day line and juice: -110 needs 52.4%,
   -120 needs 54.5%).
7. Audit the input data before modeling: missing values by season, stale fields, sign conventions.

## What actually held up in testing
- **6-point teaser legs on every dog +1.5 to +2.5 (no model):** 72.7% (1999-2014) / 77.0% (2015-22) /
  77.3% (2023-26) per leg; with game total <= 44: 75.9% / 77.4% / 78.9%. A 2-team -120 teaser needs 73.9%
  per leg. DK's teaser price was never checked by a tool. (`v2/dig.py`)
- **NFL home QB change -> Under:** 56.5% / 54.5% (rule scan, `audit/rule_scan.py`).
- **College spread, rebuilt model, edge 2+ pts vs game-day line:** 55.2% of 507 / 54.3% of 361 (2018-22 /
  2023-26); all games only 50.1% / 52.0%. (`v2/cfb2.py`)
- Betting EARLY (vs the opener) tested ~56-57% for the old NFL model - Chris rejects early betting.
- Everything else (spreads/totals on every game, NFL props vs DK prices) was never proven live.

## Things tested that did NOT help (don't re-test without a new reason)
Opponent adjustment (NFL), special teams by unit, referee crew, pace, backup skill players, median ratings,
season carry-over changes, turnover/close-game luck, travel/time zones/division/byes, coach tenure,
returning starters, OL injuries, run-vs-run-defense matchups, self-correcting on own misses,
recency-weighted training, kNN "similar games", logistic cover model, player's own hit rate for props.
Details and numbers: `README.md` sections from "V2 flaws" onward.

## Data available (all free)
- nflverse (games/lines/weather/QBs, play-by-play, player stats, injuries, snaps, rosters, Next Gen Stats).
- ESPN JSON APIs: scoreboard, summary (injuries, game-day inactives ~90 min before kickoff, box scores).
- CollegeFootballData API (`api.collegefootballdata.com`, the session proxy adds the key): lines from
  DraftKings and others, games, stats. Spread there is the home team's number (-7 = home favored).
- cfbfastR / sportsdataverse play-by-play for college.
- Open-Meteo forecasts (`scripts/fetch_weather.py`).
- The Odds API (DK prices, props): **500 credits/month only**; a props pull costs ~11 per game. Use
  sparingly; Chris is staying on the free plan.

## Chris's rules file
`CLAUDE.md` (repo root and `football-model/`) - read it. Update rule 4 there: prop unders are allowed
(Chris, Nov 24), priced correctly.
