# v8 props model + DK price log - written and committed BEFORE any v8 result was computed (Nov 26 2026, ~8 PM CT)

Chris (Nov 26): "start v8 and the price log". v6/v7 showed the v3 props projection misses weather, the game's
expected score and target/carry redistribution (printed as notes only). v8 builds them INTO the chance.

## v8 projection
proj8 = proj3 (v3 weighted average x opponent factor, unchanged) x f, where f is fit per stat by OLS on TRAINING rows
of ratio = actual / proj3 (clipped to [0, 5]) on:
- itt: the player's team implied total from the closing lines minus 22 (fixed centre)
- bad: v6 BAD weather (outdoor/open only; else 0)
- rec_out: WR/TE whose team's key receiver is out (v7 B definition); 0 for others
- rb_out: RB whose team's lead RB is out (v7 B definition); 0 for others
f is clipped to [0.5, 1.5]. A Pricer (same v3 method) is then trained on proj8 for the same training seasons.
Stats: passing yards, rushing yards, receiving yards, receptions, anytime TD.

## Test (same split and lines as v3 PROTOCOL amendment 4)
- EARLY: fit + Pricer on 2013-18, scored 2019-22. LATE: fit + Pricer on 2013-22, scored 2023-26.
- Lines from proj3 (same for both models): yards 0.6x / 1.0x / 1.4x rounded to x.5; receptions proj3-1 / proj3 /
  proj3+1 rounded; TD 1+. Rows: players with 3+ prior qualifying games, both models priced.
- Score = Brier (lower is better). v8 REPLACES v3 for a stat only if its Brier is lower in BOTH periods.
- Calibration (LATE, same rule as v3: every decile with 50+ checks within 3 pts) decides the "calibrated" label.

## If a stat passes
`card.py prop` prints the v8 chance as the main number (v3 shown beside it); the v6/v7 notes for that stat are
dropped (already inside v8). Stats that fail keep v3 + notes. v3 stays frozen and on file.

## DK price log (starts now; this is the data needed to ever test against DK)
Every DK prop price that goes through `card.py prop` (from Chris's slips/screenshots) and every Odds API prop pull is
appended to `v8/prices/dk_props.csv`: time, game, player, stat, line, DK Over/Under price, v3 and v8 chances. The
scoreboard grades them. After 300+ graded priced props, test: does betting when model chance - DK break-even >= 5 pts
win more than break-even? (rule fixed now; not run before 300).

## Amendments
1. (Nov 26, before any v8 result.) Price-log test counts only prices logged BEFORE kickoff (a price logged after
   kickoff is a live price). result column = the player's actual stat from the ESPN box score (void if he did not play).
2. (Nov 26, after results.) Live inputs: team total from DK via ESPN for the player's next game (blank once a game is
   live -> 0); bad = v6 forecast mapping; outs from ESPN's list; key players from v7/live.py. 129 DK prices from Chris's
   Nov 26 8:32 AM CT screenshots back-filled into the price log (v3 chances recomputed from the same data).
3. (Nov 27.) Removed every 'card.prop' row logged so far (test runs by Claude with made-up or simulated prices, plus
   two real prices re-entered after kickoff). Only Chris's screenshot prices remain. Tool test runs with prices must
   not be logged - use no --over/--under when testing.
