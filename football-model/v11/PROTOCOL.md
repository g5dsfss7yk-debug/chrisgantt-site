# v11 combined game model - written and committed BEFORE any v11 result (Nov 26 2026, ~11:15 PM CT)

Chris (Nov 26): "the V3 picks model has gaps on variables... combine the 2 models" -> "build both".
v11a = v3 game model + the new variables. v11b = v3 game model + team yardage built from the props projections.
v3 stays frozen; v11 replaces v3's spread or total picks only by the rule below.

## Base
v3's saved walk-forward features (v3/results/nfl_backtest.pkl: same ratings, H=16 G=0, closing lines) and the same
OLS walk-forward (fit on all earlier seasons from 2003, predict each season). Same bet rules and -110 grading as v3.

## New variables (all known before kickoff in live use)
- Weather (v9 hourly, outdoor/open only; domes and games without data = 0): gustx = max(gust - 15, 0) mph,
  rainx = min(rain, 1.0) in, coldx = max(40 - temp, 0) F.
- Backup QB: starter's earlier starts in the data (games as his team's QB in v3 features, any season) < 4 -> 1.
- Key receiver out / lead RB out (v7 definitions, 2012+; 0 before): count per team.
- Defensive starters out (v7 definition, 2012+; 0 before): count per team.
v11a SPREAD_X = v3 + [backup_h - backup_a, recout_h - recout_a, rbout_h - rbout_a, dout_h - dout_a]
v11a TOTAL_X  = v3 + [gustx, rainx, coldx, backup_h + backup_a, recout_h + recout_a, rbout_h + rbout_a, dout_h + dout_a]
v11b: v3 X plus props yardage: for each team, sum of v3 props projections (passing yds of its QB with the most
attempts-history, rushing yds of every RB/QB, from players in that game's snap counts - i.e. active) ->
SPREAD_X + [yds_h - yds_a], TOTAL_X + [yds_h + yds_a]. Props exist from 2013, so v11b is fit from 2013.

## Periods and pass rule
v11a: EARLY 2006-16, LATE 2017-26 (same as v3). v11b: EARLY 2014-18, LATE 2019-26 (first season with a fit).
Bet types: spread all games / edge 1+ / edge 2+; total all games / edge 1+ / edge 2+.
- TESTED PICK: v3 rule - both periods >= 52.4%, combined binomial p < 0.05, 100+ bets each.
- v11 REPLACES v3 for spreads (or totals) only if its all-games hit rate beats v3's in BOTH periods (same seasons).
Everything is printed next to v3 on the same games. Nothing else is tried.

## Amendments
1. (Nov 26, BEFORE any v11 result - nothing was run.) Chris: "I meant build one model that covers everything."
   v11a and v11b are MERGED into ONE game model:
   SPREAD_X = v3 + [backup_h - backup_a, recout_h - recout_a, rbout_h - rbout_a, dout_h - dout_a, yds_h - yds_a]
   TOTAL_X  = v3 + [gustx, rainx, coldx, backup_h + backup_a, recout_h + recout_a, rbout_h + rbout_a, dout_h + dout_a, yds_h + yds_a]
   Because props yardage starts in 2013, the ONE model is fit from 2013 and tested EARLY 2014-18 / LATE 2019-26,
   always next to v3 on the same games. yds = the starting QB's (most offense snaps) prior passing-yards average plus
   every active RB/QB's prior rushing-yards average (v3 props weighted average of games BEFORE this one, no opponent
   factor - the game model already has the defenses). Same pass and replace rules as above.
   Props stay v8 (same inputs). One card (v11/card.py) prints games + main-player props + every check in one run.
