# HANDOFF - Nov 27 2026 (read the repo-root CLAUDE.md first, then this)

Branch: `claude/modest-galileo-zg0mve` (repo g5dsfss7yk-debug/chrisgantt-site). Everything is under `football-model/`.
Chris bets $2/pick on DraftKings, game day only. He is frustrated by losses - be plain, never argue his game-day
observations away with averages (CLAUDE.md rule 6h), never put untested Overs in bad-weather parlays.

## What exists (each has PROTOCOL.md written BEFORE results + RESULTS.md)
| Version | What | Status |
|---|---|---|
| v3 | base game model (ratings + QB + DK line), props v3 | frozen; game side replaced by v11 on the card |
| v4 | PRICE GAP (DK moneyline vs spread) | TESTED PICK (53.9%/53.9%); NOT A BET when juice needs > 53.9% |
| v5 | Odds API price checker DK vs Pinnacle (`v5/pricecheck.py`), `v5/gameday.py` | credits were 0 on Nov 26 |
| v6 | weather Under (ESPN forecast gusts 25+ / rain 50%+) | TESTED PICK (55.9%/56.7%) |
| v7 | overlooked variables: key receiver out, lead RB out, team total | prop notes (now inside v8) |
| v8 | props model = v3 projection x weather/key out/lead RB out/team total | replaced v3 props (all 5 stats) |
| v9 | weather SEVERITY (Open-Meteo hourly): gusts 30+ Under; heavy rain cuts receiving/receptions | TESTED (55.4%/59.3%) |
| v10 | learning layer: learns model-vs-DK weight from graded DK prices | warm-up; after day 1 it trusts DK (0.05 model / 1.18 DK) |
| v11 | ONE combined game model (v3 + weather severity + backup QB + players out + props yardage) | drives card spread/winner/total; LEAN (52.5%/50.8% spreads) |
| teaser | 6-pt teaser leg on dogs +1.5..+2.5 | TESTED PICK (75.5%/77.1%, needs 73.9%) |

## Game day
1. `python football-model/v3/card.py nfl --week N` - every game: v11 numbers + inputs (v3 beside), tested picks
   (>> TEASER LEG / PRICE GAP / WEATHER UNDER), every check (** lines). Re-run ~90 min before kickoff (inactives).
2. Props: `python football-model/v3/card.py prop "Name" stat line --over P --under P` - v8 chance, v10 learned chance,
   every check. ONLY pass --over/--under with Chris's REAL DK prices (they go to v8/prices/dk_props.csv). Test runs: no prices.
3. After games: `python football-model/v3/scoreboard.py` (grades picks + DK price log, refits v10).
4. Commit + push the pick log after every card run (the stop hook asks).

## Checks the tools print (CLAUDE.md rule 6 a-k) - never skip, never give a pick without them
Injuries/inactives (ESPN), QB, BACKUP QB (<4 starts), TEAMMATES OUT, ROLE CHECK, line move 2+ (CHANGE), weather + SEVERE
WEATHER (Open-Meteo hourly: heavy rain, snow, gusts 30+, freezing) -> passing/receiving/receptions Overs NOT VERIFIED,
TOO GOOD TO BE TRUE (15+ pts over DK), PRICE CHECK (>2 h before kickoff), bet cap (3 per game, no same-team parlay legs).

## Live record (Nov 25-26: GB@LA, CHI@DET, PHI@DAL, KC@BUF)
Tested picks: teaser legs 1-1, weather Under 1-0, price gap none qualifying (DET +1.5 was NOT A BET, lost).
Leans: spreads 1-2-1, totals 1-3, winners 3-1. Props 5-21 (every logged prop was an Over; KC@BUF storm 0-15).
DK price log: 127 prices (Chris's Nov 26 screenshots), 116 graded; DK test at 300. Day 1: DK's prices beat the model
(Brier 0.220 vs 0.231). Lesson so far: bet TESTED PICKs; treat big model-vs-DK gaps as warnings; ask for Under prices too.

## Open items
- Raspberry Pi app built (`football-model/pi/`, README there): Pi 4 4 GB, headless. Cloud sessions CANNOT SSH (port 22
  refused, tested Nov 26). Chris chose nothing yet: (1) install Claude Code on the Pi and let it follow pi/README.md, or
  (2) Chris pastes a command block over his own SSH (ask his Pi username first). Keys needed on the Pi: CFBD_API_KEY,
  DDS_API_KEY (Chris has them; never ask him to paste keys in chat).
- Open-Meteo free daily limit was used up on Nov 26/27 by the v9 history download; live severe-weather flags may say
  "forecast not available - check by hand" until it resets.
- Scheduled cloud tasks: "NFL game-day picks - Sunday" (Sun 11:04 CT) and "Thu/Mon night" (6:04 PM CT) run v5/gameday.py.
- Next tests worth writing (protocol first): DK-price test at 300 graded prices (v8 rule), v10 proof at 300 walk-forward.
- Network hosts added to this environment (Chris approved): archive-api.open-meteo.com, geocoding-api.open-meteo.com.

## Do not
- Change a frozen model without a new protocol committed first. Quote records not in RESULTS/frozen/scoreboard output.
- Log test prices into the DK price log. Retry Pinnacle/DK scraping (blocked by the permission classifier).
