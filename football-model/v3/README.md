# Football model v3 (built from scratch Nov 25 2026)

Start here: `PROTOCOL.md` (rules set before testing) -> `RESULTS.md` (what passed) -> run the card.

Setup: `pip install pandas numpy pyarrow`. Run from `football-model/`. Data downloads itself into `data/v3/`
(gitignored): nflverse schedules + play-by-play (`python v3/fetch_pbp.py 2002 2026`, ~1 minute), nflverse weekly
player stats (`data/v3/stats/`, see HANDOFF), CollegeFootballData (session proxy adds the key), ESPN.

| Command | What it does |
|---|---|
| `python v3/card.py nfl --week 12` | Every NFL game: spread, winner, total (LEAN) + `>> TEASER LEG` (TESTED PICK). DK lines/prices from ESPN. Logs picks. |
| `python v3/card.py cfb --date 20261128` | Every FBS game that day (all LEAN) + `DK GAP` flag. Logs picks. |
| `python v3/card.py prop "Josh Allen" passing_yards 235.5 --over -115 --under -105` | Fair price of Over and Under; value at DK's price |
| `python v3/card.py props --team BUF` | Fair prices for a team's players near their projection |
| `python v3/scoreboard.py` | Grades `v3/picks/log.csv` from ESPN finals; live record by bet type |
| `python v3/audit_data.py` | Data audit (missing values, sign checks, stale QBs) |
| `python v3/backtest_nfl.py late`, `python v3/backtest_cfb.py late`, `python v3/props.py` | Reproduce the tests |

Files: `data.py` loaders, `nfl.py` / `cfb.py` game models, `props.py`, `grade.py` (pass/fail rule),
`frozen.json` (settings + tested records the card prints). Nothing from `nflmodel/`, `v2/`, `cfbmodel/` is imported.

Frozen: no changes except proven bugs (log them in PROTOCOL.md "Amendments"). Judge v3 only by `scoreboard.py`.
