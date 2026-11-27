# v7 overlooked-variables test - written and committed BEFORE any v7 result was computed (Nov 26 2026, ~6:40 PM CT)

Chris (Nov 26): "Build what you can into the model." These are ADD-ON flags; the frozen v3 model is not refit.
Not built, and why: college weather (CFBD weather needs a paid tier - checked, HTTP 401), late-season motivation
(no clean historical clinch/elimination data - building it would mean guessing), public/sharp betting % (paid).
Re-tests of ideas the brief lists as "did not help" (OL injuries, travel, referees...) are NOT run.

## Data
- nflverse closing spread/total (schedules), weekly player stats (2012-26), snap counts (2012-26, who played),
  v6 game-time weather text (2006-26). Teams' "did not play" = not in that game's snap counts (matched by name + team).
- Implied team total (ITT): home = (total + spread)/2, away = (total - spread)/2 (nflverse spread > 0 = home favored).

## Props tests - same method as v6: line = v3 projection rounded to x.5 (props.half); actual hit rate vs the v3
Pricer's predicted chance for that side. EARLY: Pricer trained 2013-18, scored 2019-22. LATE: trained 2013-22,
scored 2023-26. Players need 3+ prior qualifying games. Pass: gap >= +3.0 pts in BOTH periods, 100+ in each,
combined one-sided binomial p < 0.05 vs the mean predicted chance.
A. Game script (all players, the player's team's ITT and spread):
- A1 passing yds OVER when ITT >= 26.5; A2 passing yds UNDER when ITT <= 19.5
- A3 rushing yds OVER when ITT >= 26.5; A4 rushing yds UNDER when ITT <= 19.5
- A5 receiving yds OVER when ITT >= 26.5; A6 receiving yds UNDER when ITT <= 19.5
- A7 RB rushing yds OVER when the team is favored by 7+; A8 QB passing yds OVER when the team is a 7+ underdog
B. Teammate out:
- Key receiver = WR/TE/RB with >= 18% of his team's targets over his last 3 games played this season, who played in
  one of the team's previous 2 games and does NOT play this game. Then every OTHER WR/TE on that team:
  B1 receiving yds OVER, B2 receptions OVER.
- Key RB = RB with >= 50% of team carries over his last 3 games played (same played/not-played rule). Then every
  OTHER RB on that team: B3 rushing yds OVER.
C. Defensive starters out (starter = average defense snap share >= 60% in the team's previous 3 games, played in
  2 of them; out = not in this game's snap counts):
- C3 opposing QB passing yds OVER when the defense has 2+ starting DBs (CB/S/FS/SS/DB) out.
D2 Cold (outdoor/open, game-book temperature <= 32 F): passing yds UNDER.
E. Bad weather (v6 BAD definition): E1 receptions UNDER; E2 anytime TD - NO TD (rate of 0 TDs vs predicted).

## Game tests - graded at -110 (needs 52.4%), pushes out, pass rule as v3 (both periods >= 52.4%, combined
binomial p < 0.05, 100+ bets each period)
- C1 total OVER at the closing total when either defense has 3+ starters out. EARLY 2012-18, LATE 2019-26.
- C2 spread: the team whose OPPONENT has 3+ defensive starters out while its own defense has <= 1 out, at the
  closing spread. EARLY 2012-18, LATE 2019-26.
- D1 cold (<= 32 F) total UNDER. EARLY 2006-16, LATE 2017-26.

## Multiple tests
21 tests are run. The both-periods rule cuts luck, but about 1 false pass is possible; a pass is a flag, judged
live on the scoreboard. Nothing else is tried; no thresholds are changed after results.

## If something passes
Card: game passes print ">> <NAME>" as TESTED PICK (NOT A BET when DK's juice needs more than the lower tested rate).
Props: passes print a note on the prop line with the tested numbers; v3 chances are not changed (frozen). On game day
"out" comes from ESPN's inactive list and starters from this season's snap counts. Results: v7/RESULTS.md.

## Amendments
1. (Nov 26, AFTER results.) Hook-up: passes A1, A2, A6, B1, B2, B3 print as notes on `card.py prop` (v3 chances not
   changed). Team total = DK total/spread via ESPN for the player's next game; "out" = ESPN list Out/Doubtful/IR
   (inactives on game day); key receivers/RBs from this season's weekly stats + snap counts (v7/live.py). The
   TEAMMATES OUT flag stays (rule 6c); B1-B3 now give its tested direction. No game-level test passed: nothing added
   to the game card. Found after the fact, NOT a pick: A8 (QB as 7+ dog) went the OTHER way (-7.1 / -10.2 pts).
