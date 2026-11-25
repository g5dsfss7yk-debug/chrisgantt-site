# v5 price checker (Nov 25 2026) - `python football-model/v5/pricecheck.py nfl --markets spreads,totals,h2h`

What it does: DraftKings' price vs a sharp book's fair price (vig removed). Pinnacle first; otherwise the median of
Circa/BetOnline/LowVig. Only identical lines are compared. VALUE = EV >= +2% at DK's price (rule set before any result).
This is the documented method behind winning soft-book bettors (Kaunitz et al. 2017, arXiv 1710.02824: 8.5% on 256 real
bets before limits; an independent 14-season analysis of soft-book bets vs Pinnacle: 3.8% ROI, 1.9% since 2023 - both
from published reports, NOT re-tested here). NOT backtested on DK here (odds history needs a paid Odds API plan).
VALUE picks go to v3/picks/log.csv and are graded by `python football-model/v3/scoreboard.py`.

Credits: 1 per market per league per pull (all games in one call). `--cached` re-reads the last pull for free.
Nov 25: 2 credits left this month (497 used before this build, 1 used for the first test).
First pull (Nov 25, NFL spreads): 34 DK spreads compared, 0 VALUE; DK main spreads were 0 to -9% EV vs sharp.
GB +2.5 -110 (v4 price-gap pick) was -3.2% vs Pinnacle.

Where value usually is (per the sources above, not checked here): moneylines, totals, alt lines and props at soft books,
and lines that have not moved yet after news. Props need the per-event endpoint (~1 credit per market per game) and a
sharp book that posts props - not affordable on 2 credits.

Nov 25 second pull (NFL moneylines + totals, 2 credits, 0 left this month): 66 DK prices compared. With proportional vig
removal two longshot moneylines showed +2% (PHI +364, TEN +780); with the power method they were -5.1% and -18.3%.
Rule amended before any grading: VALUE must hold under BOTH methods. Result: 0 VALUE on spreads, moneylines, totals.
