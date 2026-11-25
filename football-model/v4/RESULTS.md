# v4 results (Nov 25 2026) - `python football-model/v4/backtest.py`, rules in PROTOCOL.md (committed first)

LATE periods were re-used from v3, so this is weaker evidence than v3's. Full table: results/v4_results.txt.

**Passed:** NFL moneyline-vs-spread gap 1+ (bet the spread side DK's moneyline favors): 53.9% of 256 (2007-16; 2006 had
no earlier moneylines to fit on) / 53.9% of 319 (2017-26). Combined p = 0.033 vs 50%, but if the true rate were 52.4%
(break-even at -110) a record this good would happen 25% of the time - NOT proven profitable. 2025-26: 50%.
Picks the underdog 83% of the time. About 27 bets a season. Graded at -110: at worse DK juice (e.g. -122, needs 55.0%)
it is not a bet, and the card says so.

**Failed:** totals by chance (fixes the Over bias - now 36% Overs NFL / 29% CFB - but 51.6% / 50.5% NFL, 50.6% / 51.1% CFB),
ratings-only spread models (worse than the line: NFL squared error 175.2 vs line 162.4; CFB 307.8 vs 229.0),
v3+ratings agreement, CFB moneyline-vs-spread gap (52.2% of 312 in 2022 / 53.7% of 951 at DK 2023-26 - failed EARLY by
0.2 points; shown on the college card as a LEAN).

Main finding stands: no stats model here predicts margins better than DK's line. The only things that tested above
break-even use the market's own prices (teaser legs through key numbers, moneyline/spread disagreement).
