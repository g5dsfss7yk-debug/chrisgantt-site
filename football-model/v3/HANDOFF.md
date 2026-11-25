# v3 handoff (Nov 25 2026) - read CLAUDE.md first, then this

## State
- v3 is a from-scratch build (brief: NEW_MODEL_BRIEF.md). Rules committed before testing (PROTOCOL.md, commit 7431054),
  settings picked on EARLY only, LATE checked once, then FROZEN (frozen.json). Results: RESULTS.md.
- Only TESTED PICK: NFL 6-pt teaser leg on every dog +1.5..+2.5 (75.5% / 77.1%, need 73.9%). Everything else is LEAN.
- Branch: `claude/modest-galileo-zg0mve` (includes all of `claude/pensive-wright-l3v5cy` merged in).

## Game day
1. `python football-model/v3/card.py nfl --week N` (ESPN's default NFL scoreboard can still show last week - pass --week).
2. `python football-model/v3/card.py cfb --date YYYYMMDD` (~30 s, refreshes CFBD data for the season).
3. Props on request: `python football-model/v3/card.py prop "Player Name" receiving_yards 54.5 --over -115 --under -105`.
   Stats: passing_yards, rushing_yards, receiving_yards, receptions, anytime_td. Check ESPN that the player is active.
4. After games: `python football-model/v3/scoreboard.py`.
Re-running a card before kickoff overwrites that game's logged picks (latest game-day price wins).

## Fresh container
`pip install pandas numpy pyarrow`; `python football-model/v3/fetch_pbp.py 2002 2026`; weekly player stats for props:
`for y in $(seq 2012 2026); do curl -sL -o football-model/data/v3/stats/w_$y.parquet https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_$y.parquet; done`
(make `football-model/data/v3/stats/` first). Refresh the current season's pbp/stats each week (`fetch_pbp.py 2026 2026 --force`).

## Do not
- Change settings, add features, or re-test against 2006-2026 to "improve" v3. That is how the last builds fooled themselves.
  A new idea = a new protocol written first, judged on games after it is written.
- Quote any record that is not in RESULTS.md / frozen.json / scoreboard.py output.

## Open items
- Totals lean Over by construction (RESULTS.md flaw 1). Candidate fix for a v3.1 protocol: compare the predicted median.
- DK teaser price/push rule never checked by a tool. Ask Chris what his DK slip shows for a 2-team 6-pt NFL teaser.
- Odds API key use was blocked in this session; v3 does not need it (DK prices come from ESPN's scoreboard).
