**v3 (Nov 25 2026) replaces everything below: read `v3/HANDOFF.md`.**

# HANDOFF - Nov 15 2026, ~1:15 CT (read CLAUDE.md first)

**New agent: read `AGENT_HANDOFF.md` first - it is the full standalone handoff.**

**Branch: `claude/pensive-wright-l3v5cy`** holds everything below. `claude/football-model` is ONE SESSION BEHIND
(no fixes, no dig, old card) - Chris has not said to push there. Start the new chat on pensive-wright.

## State
- V2 only: v2/nfl.py (game model), v2/card.py (card), v2/props.py + v2/props_card.py (props), v2/dig.py, v2/improve.py.
- Chris does NOT bet early. Game-day records only, always 2015-22 / 2023-26. Records are in CLAUDE.md rule 5.
- **Card layout (Chris, Nov 15): a pick on EVERY game, tested teaser legs marked ">> TEASER LEG", every "** CHANGE"
  line shown** (QB out/changed per ESPN, line or total moved 2+ since the opener, wind 15+, rain, skill players out).
  Do not switch the card to "tested bets only" - Chris turned that down.
- Fixed today (README "V2 fixes Nov 15"): missing wind (caused the Over lean), unscaled features, card fits on the
  game-day line, QB-change bug for unlisted starters, card skips games already started.
- Tested: spreads all games 52.4% / 50.7%, edge 1+ 52.8% / 55.0%, edge 2+ 57.0% of 214 / 58.1% of 62 (small);
  totals 53.2% / 51.7%. No proven edge on sides or totals - they are fun picks.
- **Tested bets:** (1) teaser leg on EVERY dog +1.5..+2.5, no model (v2/dig.py): 72.7% (1999-2014) / 77.0% / 77.3%;
  total <= 44: 75.9% / 77.4% / 78.9%; needs 73.9% at -120. 57 of the last 64 weeks had 2+ such dogs.
  DK's teaser price is NOT checked by any tool - Chris reads it on the slip.
  (2) home QB change -> Under 56.5% / 54.5% (audit/rule_scan.py).
- Dig also tested and rejected: moneylines by price, fading lines vs market ratings, nfelo vs the close.
- Props vs DK prices: NOT proven. After NE@DET only: model-over-DK rungs 0-11. Parlays only multiply leg edges;
  use `run.py parlay --boost` when Chris has a DK boost.
- Chris is frustrated that sides/totals have no edge. Be straight: say what is tested, give the pick anyway,
  never invent an edge.
- Odds API: 9 credits this morning, one more call made at 12:45 CT (cost not seen). Use --cached; saved prices
  are from 12:45 CT (in a fresh container the cache is gone and --cached will call the API).

## Today (Nov 15)
- NE@DET: DET won 35-10, total 45 (line 50.5). #166, #174, #176, #181 lost.
- #160 CLE Under 40.5: Watson started (ESPN box score) - condition met.
- #161 LV Under 40.5: LV inactives not posted at 12:40 CT; schedule lists Mendoza. ESPN lists SEA QB Darnold OUT.
- Card flags to check: ESPN lists Minshew (ARI) and Huntley (BAL) on injured reserve while the schedule has them
  starting - picks for those games NOT VERIFIED. #162 BAL Under (Mon) only if Huntley starts.
- Late-game card (DK 12:45 CT): LV +6.5 / Under 40.5; LA -9.5 / Over 38.5; SF -4.5 / Under 55.5; CIN -3.5 / Over 49.5;
  BAL -4.5 / Under 38.5. No dog +1.5..+2.5, so no tested teaser leg. SF and BAL are the edge 1+ spread picks.

## Next steps
1. After ~3:30 CT: `PYTHONPATH=. python audit/v2_vs_dk.py` (8 early games; it took 10+ minutes here and had not
   finished - run it in the background). If model-over-DK rungs lose money again, props are fun-only; if they
   make money, build parlays from those leg types. Then `python recs.py grade`.
2. Ask Chris which of today's bets he placed (`recs.py placed`). Placed record before today: 3-12, net -$30.
3. Ask Chris whether to push this branch's work to `claude/football-model`.
4. Still open in the code: props_card.py alt spreads still fit on the opener and were not re-calibrated after
   the scaling fix; card QB names come from nflverse and can be stale (the ** CHANGE lines catch ESPN conflicts).

# NOV 15 2026: OLD NFL MODEL SCRATCHED. Use v2/card.py (see CLAUDE.md rule 5). Tests: v2/test_nfl.py, v2/test_teaser.py, v2/grid.py.

# Handoff (Nov 9 2026)

Chris bets $3 per pick on DraftKings for fun: prop parlays and teasers. Wants plain, short answers.

## Ground rules
- **NO GUESSING (Chris, repeated).** Every number given to Chris must come from a tool's output
  (run.py, recs.py, audit/*) or a tested result, and say which. No eyeballed chances ("coin flip",
  "maybe 30%"), no estimated cash-out values, no arithmetic on assumptions. If no tool gives the
  number, say "I don't know" or run a tool that does. Never recommend against a tool's output on gut.
- Before any pick: QB (incl. Out/Doubtful -> backup), injuries, weather (forecast + ESPN, rain flag),
  surface, form. The cards and `run.py props` print these; read the NOT VERIFIED list.
- Chris's DK has NO receptions, NO rush attempts, NO unders. Prop legs = yards / TDs / passing "X+" ladders.
- **Only these are bets** (CLAUDE.md rule 5, README "Rebuild test"/"Rule scan"/"BET EARLY"/"Miss review"):
  1. NFL 6-pt teaser legs on dogs +1 to +2.5 (79.4% per leg 2023-26).
  2. NFL model spread LEAN/STRONG bet EARLY (`run.py early`, 56.7%/57.1% vs opener); on game day
     STRONG only. The card SKIPs 0-3 pt favorites and 7.5-10 pt dogs (48% / 52%).
  3. NFL home-team QB change -> Under, once the change is confirmed (54.5% 2023-26).
  4. College SITUATIONAL total 56%+ from `cfb.py card` (53.4% 2023-26).
- RETIRED (tested, no edge): old college model (spreads 48.2%, totals <50%; hidden unless
  `cfb.py card --old`), NFL totals, pregame props, live props. Do not recommend them.
- Log every recommended combo: `python recs.py add ...`; grade: `python recs.py grade`.

## New this session (Nov 9, MNF)
- `run.py odds` works live (key read from DDS_API_KEY). Fixed a bug: no-vig math pooled each book's
  main line with its alternate ladder at the same number, so sharp chances read ~42% instead of ~50%.
  After the fix DK main lines show only normal juice (-1% to -6%); sharps price main lines only,
  so ladder rungs are checked with the model (`run.py props --line`, one rung per player per run).
- Graded: fun 2-6. #9-#11 (TB@CHI, SNF Nov 8) still pending: ESPN feed still listed it "scheduled" on Nov 9.
- Logged #12 (backed, model edge): Aaron Jones 30+ rush + Jordan Addison 40+ rec. Caution: sharp
  main lines (Jones 33.5, Addison 40.5 at ~50%) disagree with the model (medians 54 / 48).
- Logged #13 (fun): James Cook 60+ rush + Cook anytime TD.

- Clock note: the container's "today" is UTC; at Nov 9 01:10 UTC it was still Sun Nov 8 8:10pm ET.
- SNF TB@CHI: logged #14 (backed, model edge) Swift 60+ rush + Loveland 40+ rec; #15 (fun) same + Gainwell 20+ rush.
  Model's Mayfield passing projection (~100) comes from TB's wk 7-8 run-outs (11 and 3 pass attempts).
  Tried skipping team <15-attempt games in averages (props.LOW_PASS_GAME): Mayfield -> 176, but
  2023-26 passing MAE 61.40 -> 61.57, so it is OFF. When a QB's recent games were freak low-volume,
  trust the market line over the model.
- Game-day inactives (ESPN, ~90 min before kickoff) now set players Out in all checks/projections.

- Added `props --scan TEAM` (DK ladder edge scanner) and `run.py parlay` (boost EV). README "Betting rules".
- Chris: no gut overrides - recommend what the tools say (see README). Earlier I wrongly downgraded
  model legs (Jones, Gainwell, Mayfield) on market disagreement.

- Live model built (`run.py live`), audited 2023-26; first use: #16/#17 Irving 60+/70+ at halftime TB@CHI.

- RE-EVALUATION (Nov 10, Chris: "don't patch"): pregame props are 5-6 live vs 67% predicted; the
  audits never tested picks against DK prices (selection: model-vs-book disagreements). Built the
  DK-price test: `props --scan all` archives every rung -> `audit/vs_dk.py` grades profit per edge
  bucket. Pregame props NOT backed until it shows profit. Option for Chris: paid Odds API
  historical props (2023+) to run audit E on past seasons now instead of waiting.

## To do next
0. Before every slate: `python run.py props --week N --scan all`; after: `python audit/vs_dk.py`.
1. `python recs.py grade` - #9-#15 pending.
3. Idea: flag props where the model median is far from DK's main line (role/volume news the model lacks).
2. When model and sharp books disagree a lot (Jones: model 54 yds, market 33.5), check role/usage news.
