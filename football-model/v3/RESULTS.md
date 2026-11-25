# v3 results (Nov 25 2026) - one-time LATE check, model frozen

Rules were committed first (`PROTOCOL.md`, commit 7431054), settings chosen on EARLY only, LATE run once.
Graded at -110 for sides/totals (DK standard; break-even 52.4%). Reproduce: `python v3/backtest_nfl.py late`,
`python v3/backtest_cfb.py late`, `python v3/props.py` (outputs in `v3/results/`).

## What passed
| Bet | EARLY | LATE | 2023-26 | Verdict |
|---|---|---|---|---|
| NFL 6-pt teaser leg, every dog +1.5..+2.5 (no model) | 75.5% of 273 (2006-16) | 77.1% of 442 (2017-26) | 78.8% of 222 | **TESTED PICK** |
| same, game total <= 44 (found by an earlier search) | 76.3% of 135 | 78.7% of 197 | 79.3% of 111 | **TESTED PICK** |

Break-even per leg is 73.9% for a 2-team teaser at -120. Pushes counted as losses.
Honest caveat: it clears break-even in both periods, but the margin is not proven - if the true rate were exactly
73.9%, a record this good would still happen about 6% of the time (exact binomial, 547 of 715). DK's real teaser
price and push rule are NOT checked by any tool.

## What failed (shown on the card as LEAN)
| Bet | EARLY | LATE |
|---|---|---|
| NFL spread, all games | 50.8% of 2374 | 50.6% of 2544 |
| NFL spread, edge 1+ / 2+ | 49.3% / 47.4% | 48.3% / 42.4% |
| NFL total, all games | 52.2% of 2400 | 50.5% of 2586 |
| NFL total, edge 1+ / 2+ | 52.5% / 53.3% | 49.2% / 47.1% |
| NFL moneyline, 3%+ value at closing price | ROI -3.5% | ROI -1.6% |
| NFL teaser leg, favorite -7.5..-8.5 | 75.7% of 140 | 71.1% of 228 |
| NFL home QB change -> Under (earlier finding) | 50.7% of 272 | 60.2% of 294 |
| CFB spread, all games (LATE at DK line) | 50.8% of 7402 | 50.5% of 3138 |
| CFB spread, edge 2+ | 46.7% of 210 | 25.0% of 4 |
| CFB total, all games | 49.2% of 7071 | 49.7% of 3050 |
| CFB DK line 1+ pt off other books, take DK's better side | (no DK lines before 2023) | 54.7% of 653 |

The CFB DK-gap rule cannot pass (no EARLY period). By season it was 57.6% (2023), 60.2% (2024), 48.4% (2025),
47.4% (2026) - looked at after the test, so it is information only.

## Props (calibration only; beating DK prices is NOT tested - every prop is a LEAN)
Trained 2013-22, checked 2023-26 at lines of 0.6x / 1.0x / 1.4x the projection (receptions: projection -1 / 0 / +1).
| Stat | Worst gap between predicted and actual hit rate | |
|---|---|---|
| Rushing yards | 1.0% | calibrated |
| Receiving yards | 2.3% | calibrated |
| Receptions | 3.2% | NOT calibrated (Overs a bit too high) |
| Passing yards | 3.8% | NOT calibrated (Overs a bit too high) |
| Anytime TD | 5.4% | NOT calibrated |

## Known flaws found after the freeze (not fixed - frozen; proven-bug fixes only)
1. **Totals lean Over far too often.** OLS predicts the AVERAGE total; game totals are skewed, so the average sits
   above the line. Over share of total leans: CFB 81-99% by season, NFL 66-79% (2019-26). The total LEAN is mostly
   "Over" for that reason, not because of any matchup read. A fix (compare the median, not the mean) is a NEW model and
   would have to be written into a new protocol and judged only on future games.
2. Spread/total models put almost all weight on the market line, so edges are tiny (NFL edge 2+ happened in 4% of
   EARLY games and 1% of LATE games). The model mostly restates DK's number. That is the main finding: public stats do not beat the closing line.
3. Props lines in the calibration test are synthetic (no DK line history). Real DK lines may sit where the model is
   less calibrated.
4. NFL starters for upcoming games come from the nflverse schedule (stale 3-9% of the time per the audit); the card
   flags an ESPN Out/Doubtful/IR status for the listed QB as NOT VERIFIED but does not swap in the backup.
