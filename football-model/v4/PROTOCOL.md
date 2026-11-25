# v4 test protocol - written and committed BEFORE any v4 result (Nov 25 2026)

Why v4: Chris (Nov 25) - the season ends before a forward-only test can finish; the models must be more predictive now.
v3 stays frozen and keeps its scoreboard. v4 tests a SHORT, fixed list of new ideas aimed at v3's known weaknesses.
Nothing is added to this list after results exist.

**Honesty note:** the v3 LATE periods (NFL 2017-26, CFB 2023-26) were already looked at once (v3 results). Checking
them a second time here makes them weaker evidence than v3's. v4 picks still go on the live scoreboard and are judged
there.

## Same as v3 (unchanged)
Data, periods, walk-forward fits, -110 grading for sides/totals, pass rule (both periods >= break-even, combined
p < 0.05 vs 50%, 100+ bets each period), v3 settings (NFL H=16 G=0, CFB H=12 G=0). Nothing is tuned in v4: every
threshold is fixed below.

## Ideas (all fixed now)
**A. Totals by chance, not average (fixes v3 flaw 1).** P(Over) = share of training-season residuals
(actual total - predicted total) that exceed (line - predicted). Pick Over if P(Over) > 0.5, else Under.
Bet types: all games; P >= 0.55 for the picked side. NFL and CFB.

**B. Ratings-only spread model (no market line as an input).** OLS of home margin on ratings only
(NFL: net EPA diff, QB diff, home; CFB: PPA diff, points-rating diff, home). Edge = predicted margin - line.
v3's model leaned on the line so hard that edges were tiny; this one disagrees with the market more.
Bet types: all games; edge >= 3 (NFL) / >= 6 (CFB).

**C. Moneyline vs spread disagreement (price, not prediction).** The no-vig moneyline chance maps to an expected
margin through a cubic curve in logit(chance), fit on earlier seasons (spread line on logit). When the spread is
1+ point away from what the moneyline implies, bet the spread side the moneyline favors.
NFL: nflverse closing moneylines and spreads (EARLY 2006-16 / LATE 2017-26).
CFB: moneylines exist only from 2021: EARLY 2021-22 (Bovada), LATE 2023-26 (DraftKings) - EARLY is under the usual
period, stated here in advance.

**D. Agreement filter.** Bet the spread only when the v3 model (line + ratings) and idea B point to the same side
and B's edge >= 3 (NFL) / >= 6 (CFB).

## Also reported (information, not pass/fail)
How predictive each spread model is against the market: mean squared error of predicted margin vs actual margin,
next to the MSE of the line itself, LATE period. A model only adds information if its MSE is lower than the line's.

## After the test
Passing ideas become TESTED PICKs on the card, labelled "v4 (LATE period re-used)". Failing ideas are dropped
(not shown). Then v4 is frozen like v3.

## Amendments
(none)
