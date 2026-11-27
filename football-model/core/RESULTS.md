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

## College + all variables (amendments 2-5; core/results/cfb_test2_firstqb.txt). LATE was seen once before.
Added: QB (value, backup, change), Elo, talent, returning production, rest, travel - with the 8 stats and the line.
| Bet | EARLY 2017-22 | LATE 2023-26 | p | Result |
|---|---|---|---|---|
| Spread, all games | 50.6% of 5305 | 52.8% of 3789 | 0.959 | LEAN |
| Spread, edge 2+ | 54.0% of 1064 | 54.8% of 438 | 0.078 | LEAN - above 52.4% both periods, not proven |
| Spread, edge 4+ | 55.8% of 181 | 48.0% of 50 | | LEAN (too few late) |
| Total, all games | 50.3% of 5233 | 52.1% of 3708 | | LEAN - 70% / 68% Overs |
| Total, edge 2+ | 47.2% of 869 | 55.3% of 349 | | LEAN |
| Winner, 3%+ value | ROI +19.8% (342) | ROI +0.7% (480) | 0.063 | LEAN |
EARLY squared error: margin 244.2 / total 270.4 vs line + 8 stats 243.2 / 269.8 vs line alone 243.3 / 269.3.

**Withdrawn run (leak, amendment 5):** with "starter = most dropbacks" (in-game information) spread edge 2+ was
53.9% / 57.0% (p=0.008) and winner ROI +16.4% / +7.7% (p=0.011) - both "passed". With the starter known at kickoff
(first dropback) both fail. That run is NOT a result; kept in core/results/cfb_test2.txt only as the record.

**Bottom line: still no college TESTED PICK.** Spread edge 2+ is above break-even for the fourth build in a row
(v2 55.2% / 54.3%; core 53.6% / 56.2%; core+all 54.0% / 54.8%) but no run has proven it.

## NFL game model (amendments 6-8; `python core/nfl.py`, core/results/nfl_test.txt). Every season was used by old builds.
H = 4 chosen on EARLY (4/8/16 nearly equal). EARLY 2011-17, LATE 2018-26, nflverse closing lines.
| Bet | EARLY 2011-17 | LATE 2018-26 | p | Result |
|---|---|---|---|---|
| Spread, all games | 49.5% of 1817 | 50.9% of 2336 | 0.997 | LEAN |
| Spread, edge 2+ | 52.4% of 576 | 52.8% of 176 | 0.487 | LEAN |
| Spread, edge 4+ | 54.3% of 116 | 2 of 5 | | LEAN (too few) |
| Total, all games | 49.3% of 1851 | 50.4% of 2373 | 0.999 | LEAN - 62% Overs |
| Total, edge 2+ | 52.3% of 619 | 55.0% of 327 | 0.306 | LEAN |
| Winner, 3%+ value | ROI -7.7% (836) | ROI +4.1% (505) | 0.814 | LEAN |
| **T: 6-pt teaser leg, dog +1.5..+2.5** | **76.5% of 230** | **77.1% of 402** | **0.047** | **TESTED PICK** (needs 73.9%) |
| P: price gap 1+ pt | 50.5% of 994 | 47.8% of 1098 | 0.999 | FAIL |
| W: Under, game-book wind 15+ | 55.6% of 162 | 57.2% of 159 | 0.085 | FAIL - above break-even, not proven |

EARLY squared error, margin / total: line only 175.9 / 175.2; full model 179.4 / 179.8 - the full model (8 stats,
QB, starters out, questionable, rest, weather, division) is WORSE than the closing line alone. Largest weight:
QB value (+7.2 margin per EPA/dropback). Only the teaser leg (a rule, no model) passes.
Differences from the old tests: price gap failed here (old v4: 53.9% / 53.9%, a different conversion); wind Under
here has no rain/snow (not in nflverse schedules) and only game-book wind.

## NFL props (amendments 9-10; core/results/props_nfl.txt = first run, props_nfl_floor.txt = with DK line floor)
Half-life HP = 4 chosen on EARLY. Fit on EARLY 2014-19 only, checked on LATE 2020-26. Test line = player's last-8
mean rounded to x.5 (TD 0.5). "Naive" = the EARLY share of Overs at that kind of line.
| Stat | Beats naive (both periods) | LATE worst calibration gap, first run / with floor | Calibrated? |
|---|---|---|---|
| Passing yards | yes | 6.5 / 6.5 pts | no |
| Rushing yards | yes | 50.1 (bug: lines of -0.5/0.5 yds) / 4.3 pts | yes, with floor |
| Receiving yards | yes | 4.8 / 17.2 pts | no (with floor) |
| Receptions | yes | 9.4 / 5.1 pts | no (just over 5) |
| Anytime TD | yes | 19.6 / 19.6 pts | no - under-predicts the top scorers (said 42%, hit 62%) |

**DK check (the only test against real DK prices):** 119 of Chris's logged DK prices (Nov 25-27 2026, before
kickoff): Brier model 0.2290 vs DK 0.2134 - **DK's prices were more accurate than the model.** Overs hit 33.6%;
the model said 38.0%, DK said 45.2% (DK's Over prices carry the vig). Too few to be final; same direction as the old
v10 finding (DK beat the model on day 1).
Stopped after amendment 10: further fixes after seeing results would be tuning to the test.
