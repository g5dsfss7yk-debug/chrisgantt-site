# v3 test protocol - written and committed BEFORE any v3 result was computed (Nov 25 2026)

New build from scratch (brief: `NEW_MODEL_BRIEF.md`). No code from `nflmodel/`, `v2/`, `cfbmodel/` is used.
This file fixes every rule, setting grid and pass/fail line in advance. It is not edited after results exist;
anything added later goes in a dated "Amendments" section at the bottom and is labelled as found after the fact.

## Data (audited first: `v3/audit_data.py` -> `v3/results/data_audit.txt`)
- NFL: nflverse schedules (closing consensus spread/total/moneyline + juice, scores) and nflverse play-by-play.
  Sign: nflverse `spread_line` > 0 = home favored (checked: agrees with the moneyline favorite in 100% of 4,291 games).
- Not used, because the audit found holes: schedule wind/temp (missing for EVERY outdoor 2026 game after week 4,
  62% missing in 2022), surface and referee (60% missing in 2026). Schedule QB names are stale in 3-9% of games, so
  the starter is taken from play-by-play (most dropbacks) for history and from ESPN for live games.
- CFB: CollegeFootballData games, lines by provider, per-game advanced stats (PPA, success rate).
  Sign: CFBD `spread` is the HOME number (-7 = home favored). DraftKings lines exist from 2023 on.
- Live lines: ESPN scoreboard, provider DraftKings (free). ESPN `spread` is also the HOME number (-7 = home favored),
  the OPPOSITE sign of nflverse. The card converts and prints both teams' numbers.

## Periods (fixed)
| League | EARLY (all settings chosen here) | LATE (checked ONCE) | Line graded against |
|---|---|---|---|
| NFL | 2006-2016 | 2017-2026 (to week 11) | nflverse closing line, its listed juice (-110 if missing) |
| CFB | 2014-2022 | 2023-2026 | early: median of listed books; late: DraftKings line only (games without a DK line are not bets) |
Every model is walk-forward: a game is predicted only from games played before it; regression weights are fit only
on seasons before the season being predicted.

## Pass/fail rule (same for every bet type)
A bet type is a **TESTED PICK** only if ALL hold:
1. EARLY hit rate >= break-even, 2. LATE hit rate >= break-even, 3. EARLY+LATE combined beats 50% with one-sided
binomial p < 0.05, 4. at least 100 bets in each period.
Break-even comes from the price: -110 -> 52.4%, -120 -> 54.5%. Pushes are thrown out for sides/totals.
For teaser legs a push counts as a LOSS (conservative; DK's push rule is not checked by any tool).
Everything that fails is a **LEAN**: it is still printed on every game, labelled LEAN, with its tested record.
Recent-form subset (NFL 2023-26) is also printed for information; it does not change pass/fail.

## Settings grid (chosen on EARLY only, by hit rate of all-games spread picks; ties -> simpler/longer memory)
- NFL rating memory: half-life H in {4, 8, 16} games; previous-season games count as if G more games ago, G in {0, 8}.
- CFB rating memory: half-life H in {3, 6, 12} games; same G in {0, 8}; ridge penalty fixed at 5.
Nothing else is tuned. Edge thresholds are fixed below, not searched.

## Models
**NFL spread.** Team offense EPA/play and defense EPA/play allowed (pass + run plays, win prob 10-90%), weighted by
the memory above. QB adjustment: starter's shrunk career EPA/dropback (200 dropbacks of -0.10 added as prior) minus the
dropback-weighted value of the QBs in the team's rating window, times 35 dropbacks. OLS of home margin on
[closing line, net EPA difference, QB adjustment difference, home (0 at neutral sites)], fit on prior seasons from 2003.
Edge = predicted home margin - line. Pick the side of the edge. Bet types tested: all games, edge >= 1, edge >= 2.
**NFL total.** OLS of total points on [closing total, expected EPA/play of both offenses vs the opposing defenses,
offensive plays per game of both teams, QB adjustments, dome/closed roof]. Bet types: all games, edge >= 1, edge >= 2.
**NFL moneyline.** Win chance = normal(predicted margin, sd of training residuals). Bet when chance x decimal price - 1
>= 0.03 at the listed closing moneyline. Pass rule for moneylines: ROI > 0 in both periods, 100+ bets each.
**CFB spread / total.** Opponent-adjusted team ratings by weighted ridge regression on per-game PPA (offense, defense)
and on point margin, home field in the fit; FCS teams included. OLS of home margin on [line, PPA rating diff x 70 plays,
points rating diff, home (0 neutral)]; totals on [line total, PPA sums, plays per game]. Bet types: all games,
edge >= 2, edge >= 4 (points).
**CFB DK price check.** When DK's spread differs from the median of the other listed books by >= 1 point, take the DK
side getting the extra points (late period only; DK lines do not exist earlier). CFBD does not say when each book's
line was captured - this test can only show whether such gaps mattered.

## Rules that use no model (re-tests of earlier findings, so they are NOT fresh evidence)
- 6-point teaser legs: (a) dogs +1.5..+2.5, (b) favorites -7.5..-8.5 (NFL). Break-even per leg 73.9% (2-team -120).
- (c) as (a) with closing total <= 44 - found by an earlier data search, labelled so.
- Home team's starter differs from its previous game's starter (same season) -> Under. Found by an earlier scan.

## Props (NFL)
Passing, rushing, receiving yards; receptions; anytime TD. Player's weighted per-game average (half-life 6 games, fixed)
x opponent's weighted allowed-vs-average factor for that stat. Chance of going over a line = share of past player-games
(training seasons only) with a similar projection whose result cleared the same line/projection ratio.
Test (LATE only, 2023-26): calibration - in each tenth of predicted chance, |hit rate - predicted| <= 3 points. Even if
calibrated, beating DK's prices is NOT tested (no DK price history), so every prop is a LEAN; the card prints the fair
price for the Over AND the Under so it can be compared with DK's price on the slip.

## Freeze and scoreboard
Once the LATE check runs, the code and settings are frozen (`v3/frozen.json` holds the chosen settings and git commit).
Changes after that: proven bugs only, logged in Amendments. Every card pick is written to `v3/picks/log.csv` with its
label; `v3/scoreboard.py` grades them and prints the live record by bet type next to the tested record.

## Amendments
1. (Nov 25, after the EARLY NFL grid, before any LATE result.) nflverse's listed spread/total juice is reduced-juice
   (mostly -102..-108), not what Chris pays. Sides, totals and the QB-change rule are graded at -110 (DK standard,
   brief rule 6: break-even 52.4%). Stricter than the original line; changes no setting. Moneylines stay at the
   listed closing price - DK's historical moneylines are not available, and DK's are likely worse (not checked).
2. (Nov 25, written into props.py before the props test ran.) Props calibration lines, which the protocol did not
   spell out: yards at 0.6x / 1.0x / 1.4x the projection rounded to x.5; receptions at projection-1 / projection /
   projection+1 rounded to x.5; anytime TD = 1+. Deciles with fewer than 50 checks are not judged.
3. (Nov 25, AFTER the LATE check.) Known flaw, NOT fixed: totals compare the predicted mean with the line, so the
   total leans are mostly Overs (skewed totals). Left frozen. Any fix is a new model with a new protocol.
4. (Nov 25, Chris: "I don't like averaging".) Props method test, rule written BEFORE running `v3/test_props_median.py`:
   methods (a) current weighted average x opponent, (b) median of the player's last 8 qualifying games x opponent,
   (c) player's own hit rate over the line in his last 8 games (no model). (a) and (b) priced by the same Pricer.
   Same line set for all (0.6x/1.0x/1.4x of (a)'s projection; receptions -1/0/+1). Score = Brier (lower is better).
   EARLY: Pricer trained 2013-18, scored 2019-22. LATE: trained 2013-22, scored 2023-26 (re-used - already looked at once).
   A method replaces (a) only if its Brier is lower than (a)'s in BOTH periods for that stat. Player-own hit rate was
   reported as no help in an earlier build (brief) - re-tested only because Chris asked.
5. (Nov 25, bug fix.) Prop tools did not check ESPN injuries; Puka Nacua (IR, MCL, listed Nov 22) was priced and suggested
   as a parlay leg. `card.py prop` / `props` now drop players Out/Doubtful/IR/Suspended/PUP on ESPN and flag Questionable.
   No model change.
6. (Nov 25, dropped requests restored - flags only, no model change.) Card: CHANGE line when DK's spread or total moved
   2+ since the opener; weather flag at gusts 15+ / rain chance 50%+ (was 20+ / 60%+). Props: TEAMMATES OUT flag.
   CLAUDE.md rule 6 lists every required pre-bet check.
