# core - results (rules: core/PROTOCOL.md, committed first at 0b71264 / cd85c81)

## College game model (`python core/cfb.py test`, core/results/cfb_test.txt)
Walk-forward, every game predicted only from earlier games. Rating memory chosen on EARLY only: H = 4 (H 4/8/16 gave
almost the same error: 513.0 / 513.1 / 513.1). EARLY 2017-22 at the median closing line, LATE 2023-26 at DraftKings only.

| Bet | EARLY 2017-22 | LATE 2023-26 | p | Result |
|---|---|---|---|---|
| Spread, all games | 50.6% of 5305 | 51.1% of 3789 | 0.999 | LEAN |
| Spread, edge 2+ | 53.6% of 535 | 56.2% of 288 | 0.114 | LEAN - above 52.4% both periods, but not proven (p > 0.05) |
| Spread, edge 4+ | 50.0% of 70 | 50.0% of 46 | | LEAN (too few) |
| Total, all games | 50.0% of 5233 | 51.4% of 3708 | 1.000 | LEAN - 76% of picks are Overs |
| Total, edge 2+ | 48.8% of 606 | 50.5% of 315 | | LEAN |
| Total, edge 4+ | 10/17 | 21/27 | | LEAN (too few) |
| Winner, 3%+ value | ROI +6.0% (296) | ROI +0.5% (393) | 0.313 | LEAN |

**Nothing passed. No college TESTED PICK.**

## Found after the fact (not part of the pass rule)
EARLY walk-forward squared error, margin / total: line only 243.3 / 269.3; line + all 8 stats 244.0 / 270.0;
stats only (no line) 383.3 / 310.2. Adding any single stat to the line (pass or rush EPA, success, turnovers/takeaways,
sack rate, explosive plays, return TDs, pace) changed the error by less than 0.2 - none beat the line alone.
Meaning: the closing line already prices team strength, defense, takeaways and pass rush; this model's ratings add
nothing on top of it. The old "spread edge 2+" idea came out above 52.4% again (53.6% / 56.2%) but is not proven.
