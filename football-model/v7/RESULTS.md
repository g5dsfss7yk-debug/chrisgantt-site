# v7 overlooked variables - results (rules: v7/PROTOCOL.md, committed first at adaef6c)

Run: `python v7/test_v7.py` (about 10 min) -> v7/results/v7_test.txt / .json. 21 tests; 6 passed, all props.
Props: line = v3 projection; actual vs the model's chance for that side; pass = +3 pts in both 2019-22 and 2023-26.

## Passed (now printed on `card.py prop`)
| Test | 2019-22 | 2023-26 |
|---|---|---|
| A1 QB/passing yards OVER when DK team total 26.5+ | 47.4% vs 42.6% (+4.8), n=458 | 53.0% vs 45.3% (+7.7), n=264 |
| A2 passing yards UNDER when team total 19.5 or less | 54.4% vs 45.2% (+9.2), n=412 | 53.6% vs 44.1% (+9.5), n=483 |
| A6 receiving yards UNDER when team total 19.5 or less | 60.9% vs 57.7% (+3.2), n=3377 | 61.3% vs 57.8% (+3.5), n=3859 |
| B1 WR/TE receiving yards OVER when a key receiver (18%+ targets) is out | 47.7% vs 42.8% (+4.9), n=1478 | 47.7% vs 42.7% (+5.1), n=1431 |
| B2 WR/TE receptions OVER when a key receiver is out | 52.2% vs 45.5% (+6.7) | 50.6% vs 45.7% (+4.9) |
| B3 other RBs' rushing yards OVER when the lead RB (50%+ carries) is out | 58.1% vs 42.5% (+15.6), n=291 | 60.1% vs 42.3% (+17.8), n=188 |

## Failed
- Team total and rushing (A3, A4), receiving Over at high totals (A5), RB Over as a 7+ favorite (A7): no effect.
- A8 QB passing OVER as a 7+ underdog: went the other way (46.0% vs 53.1%, 44.7% vs 54.9%). Found after the fact - not a pick.
- C3 QB passing Over vs 2+ starting DBs out: no effect. C1 total Over / C2 spread with 3+ defensive starters out: 52.9%/51.9%, 49.1%/49.5%.
- Cold (32F or less): passing Under +5.3 / +12.0 but only 80 / 91 games (needs 100 each); total Under 42.9% / 49.6%.
- Bad weather receptions Under (+2.8 / +6.1) and no-TD (+2.6 / +4.0): early period just under +3.
- Not built: college weather (paid), late-season motivation (no clean data), betting percentages (paid).

## Limits
- No DK prop prices in history: a pass shows where the v3 projection is off, not that DK's price is off.
- 21 tests: about one false pass is possible. Judged live on the scoreboard.
