# core - ONE complete model (college first, then NFL). Written and committed BEFORE any result (Nov 27 2026)

Chris (Nov 27): "I believe this whole model to be broken... take the best of the models and build a new complete
model that does not track back constantly to the old models." Order: college first, then NFL. Scope: games + props.
Carry over: the ideas that passed tests + every pre-bet check, re-tested inside this model. Defense (Chris): takeaway
rate, pass rush, defensive TDs/big plays, and separate pass and run defense - "why would you leave out any variable".

Standalone: everything lives in `core/` (code) and `data/core/` (downloads). Nothing is imported from `v2`..`v11`,
`nflmodel`, `cfbmodel`. Rules follow NEW_MODEL_BRIEF.md: settings chosen on the EARLY period only, the LATE period
checked ONCE, then frozen; judged live only on games it never saw. No hand overrides. Anything added after results
goes in "Amendments" at the bottom, dated, and labelled as found after the fact.

## College - data
- Play-by-play 2014-2026: cfbfastR (sportsdataverse-data GitHub release `cfbfastR_cfb_pbp`), free, no API limit.
- Player stats per play 2014-2026: cfbfastR-data `player_stats` (for props).
- Lines: CollegeFootballData `/lines` (one call per season and season type; free plan, 740 calls left this month).
  Spread is the HOME number (-7 = home favored). History has no spread/total juice: graded at -110 (needs 52.4%).
- Live: ESPN scoreboard/summary - DraftKings spread, total, moneyline (pickcenter), venue, weather forecast.
- Audit first (`core/audit_cfb.py`): missing values by season, sign of spread vs result, duplicate games.

## College - team ratings (walk-forward: a game uses only games played before its week)
Plays used: scrimmage plays (rush or pass, sacks included) while the offense's win chance is 5%-95% (garbage time out).
Every stat is measured on the offense's plays in that game, so each team gets an OFFENSE number (what it does) and
a DEFENSE number (what it lets offenses do / makes offenses do):
| stat | per | why |
|---|---|---|
| pass EPA | dropback | pass offense / pass defense (separate - Chris) |
| rush EPA | rush | run offense / run defense (separate - Chris) |
| success rate | play | consistency |
| turnovers | game | offense giveaways / DEFENSE TAKEAWAY RATE (Chris) |
| sack rate | dropback | PASS RUSH (Chris). Pressures are not in free college data - not available. |
| explosive plays (20+ yds) | play | BIG PLAYS allowed (Chris) |
| return TDs (INT/fumble returned for TD) | game | DEFENSIVE TDs (Chris) |
| plays | game | pace (totals) |
Opponent adjustment: for each stat, ridge regression stat ~ offense team + defense team + home (penalty 5), each game
weighted 0.5^(games ago / H) counting back from the week being predicted, last two seasons only. FCS teams are rated
like any team. The ONLY tuned setting: H in {4, 8, 16} games, chosen on EARLY-period error (below).

## College - game model
For each game, matchup terms per stat s: home expected = home OFF_s + away DEF_s; away expected = away OFF_s + home DEF_s.
- MARGIN (home points minus away): OLS on [closing spread, neutral-site flag, and (home expected - away expected) for
  every stat]. TOTAL: OLS on [closing total, and (home expected + away expected) for every stat].
- All 8 stats go in (Chris: no variable left out). No variable selection; weights are printed.
- Walk-forward: season S is predicted from a fit on 2015..S-1 (2014 is rating warm-up). EARLY 2017-2022, LATE 2023-2026.
- Choosing H: the H with the lowest EARLY mean squared error of margin + total; then LATE is run once with that H.
- Winner: chance = normal(predicted margin, residual SD from the fit); value vs DK moneyline where history has one.

## College - bets and pass rule (fixed now)
Lines: EARLY = median of listed books' closing line; LATE = DraftKings closing line only (games without one are not bets).
Bet types: spread all games / edge 2+ / edge 4+; total all games / edge 2+ / edge 4+ (edge = |model - line| pts);
winner where the model chance beats the DK moneyline's break-even by 3+ pts.
- TESTED PICK: both periods >= 52.4% at -110 (winner: positive ROI at the listed moneyline), combined one-sided
  binomial p < 0.05 against 52.4%, 100+ bets in each period. Else LEAN. Every game still gets all three picks.
- Carry-over re-tested here: "college spread edge 2+ vs the game-day line" (old v2 result 55.2% / 54.3%) is the
  edge 2+ test above. Weather Under, teasers and price gap were NFL tests - for college they are NOT tested picks.
- Known bias check (old flaw: total leans were mostly Overs): the share of Over picks is printed for each period.

## College - props (after the game model)
Stats: passing yards, rushing yards, receiving yards, receptions, anytime TD. Projection = player's exponentially
weighted per-game average (same H) x the opponent defense factor for that stat type (pass EPA / rush EPA rating,
fit on EARLY). Chance of Over/Under from the spread of (actual / projection) seen in EARLY, by stat.
Test (no DK college prop history exists - so NOT tested against DK): calibration on LATE - predicted vs actual hit
rate in 10 bins, worst gap <= 5 pts = "calibrated", else "NOT calibrated". Every college prop is a LEAN.

## College - checks the card prints (CLAUDE.md rule 6), never skipped
(a) Injuries: ESPN has NO college injury lists (checked Nov 27: 0 of 25 games) -> every pick/prop prints
    "no college injury list - check by hand" and props are NOT VERIFIED until Chris confirms the player is playing.
(b) QB: starter = most pass attempts in the team's last game; if he differs from the team's main QB this season ->
    QB CHANGE, NOT VERIFIED. (i) BACKUP QB: fewer than 4 starts in the data -> spread/total and passing props NOT VERIFIED.
(c) Teammates: a receiver or RB who missed the team's last game (no stats) -> teammates' props flagged.
(d) Line or total moved 2+ since the opener -> CHANGE. (e) Weather (ESPN forecast, outdoor only): gusts 15+ or rain
    chance 50%+ -> flagged; bad weather -> passing yds, receiving yds, receptions OVERS NOT VERIFIED.
(f) Re-run ~90 min before kickoff. (g) Role check: projection far from this season's per-game numbers -> NOT VERIFIED.
(j) Prop chance 15+ pts above DK break-even -> NOT VERIFIED. (k) Max 3 bets per game, no two parlay legs from one team.
Log: `core/picks/log.csv` (every printed pick). Scoreboard: `core/scoreboard.py` (live record next to tested record).

## NFL (second) - written into this file before any NFL result, same structure
NFL protocol is added here as an amendment BEFORE any NFL result, with the same rules (all defense variables,
early/late periods, freeze, checks a-k).

## Amendments
1. (Nov 27, BEFORE any result - implementation details, nothing run yet.) (a) "Games ago" for the rating weights =
   weekly slates ago (one slate per regular-season week; all bowls/playoffs = one slate per season). (b) Fumble-return
   TDs are flagged neither pass nor rush in cfbfastR and only 8% are flagged turnover (audit, 2023): they are counted as
   offense plays, as turnovers and as return TDs. (c) Winner p-value = one-sided t-test that the mean profit per $1
   bet is above 0 (both periods combined). (d) The game fit uses the median closing line in every season (more games);
   bets in LATE are still graded only at the DraftKings line. (e) cfbfastR 2026 play-by-play currently ends at week 12;
   the live card prints the last week its ratings include.
2. (Nov 27, Chris: "this model isn't just based on defense" -> add everything else. Written BEFORE any result with
   these variables. NOTE: LATE 2023-26 was already looked at once (amendment-free run above), so a pass here is
   weaker evidence than a first look; the live scoreboard is the clean test.)
   Added to the college game model, on top of the 8 stats (H stays 4, chosen on EARLY):
   - QB (play-by-play passer names, 2014+): starter = most dropbacks for the team in that game. qb_value = his
     dropback EPA in all EARLIER games, shrunk: sum / (dropbacks + 200). backup_qb = 1 if fewer than 4 earlier starts.
     qb_change = 1 if the starter differs from the team's previous game.
   - Elo: CFBD pregame Elo for each team (in the play-by-play).
   - Talent: CFBD team talent composite for the season (missing - mostly FCS - = that season's lowest value).
   - Returning production: CFBD percent of last season's PPA returning, faded out by week 6:
     value x max(0, 1 - (week - 1) / 5) (missing = season mean).
   - Rest: days since the team's previous game, capped at 14.
   - Travel: miles (/1000) from the team's home stadium to the game venue (CFBD venues + team locations).
   Every variable enters MARGIN as home minus away and TOTAL as home plus away. Nothing is selected or dropped.
   Weather: history is not available today (Open-Meteo archive rate-limited; CFBD weather is a paid feature) - it is
   added later in its own amendment, before its result. Injuries: no free college data - not possible.
   Same bets, same pass rule, results printed next to the first run (8 stats only) on the same games.
3. (Nov 27, BEFORE any amendment-2 result - fill rules found in the data check.) CFBD pregame Elo is complete for
   FBS-vs-FBS games but missing for ~85-99% of games with an FCS team. Missing Elo = the team's most recent earlier
   Elo; if none, the lowest Elo seen that season. Talent starts in 2015 (2014 is warm-up only). Rest: first game of a
   season = 14. Travel: team or venue without coordinates = 0. QB with no earlier dropbacks: qb_value 0, backup_qb 1.
