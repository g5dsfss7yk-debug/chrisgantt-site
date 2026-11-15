# HANDOFF - Nov 15 2026, ~12:30 CT (read CLAUDE.md first)

## State
- OLD NFL model scratched. V2 built from scratch: v2/nfl.py (game model: play-by-play ratings incl. QB pressure),
  v2/props.py (props: own history + long-run star level + opposing defense by position + QB pressure),
  v2/card.py (spread/winner/total every game), v2/props_card.py (props + alt spreads/totals vs DK).
- Chris does NOT bet early (injuries/lineup changes). Game-day records only, both periods (2015-22 / 2023-26).
- Tested game-day: spreads ~51-53% / ~49-51% (no edge either period); totals ~51% (Over bias); teaser legs
  dog +1..+2.5 69.9% / 80.0% (needs 73.9%); home QB change -> Under 56.5% / 54.5% (only bet type with an edge
  in both periods). Adding defense/pressure/star features changed accuracy <1% (v2/compare_props.py).
- Props vs DK prices: NOT proven. audit/v2_vs_dk.py grades saved DK rungs (picks/rungs_v2/). After NE@DET only
  (1 game): rungs where model beat DK by 3%+ went 0-11 / 19% and lost money. Flaws list: README "V2 flaws".
- Odds API: 9 credits left this month (500/mo; a props pull ~11 per game). Use --cached.

## Second session Nov 15 (~1:30 CT): model fixes, details in README "V2 fixes Nov 15"
- Fixed: missing wind (cause of the 2026 Over lean), unscaled features, card now fits on the game-day line,
  QB-change bug for unlisted starters, card skips games in progress. New records are in CLAUDE.md rule 5.
- Still no proven edge on spreads or totals. Spread edge 2+ is 57.0% of 214 / 58.1% of 62: watch it, small sample.
- #160: Watson started (ESPN box score). #161: LV inactives were not posted at 12:40 CT; ESPN had Darnold (SEA) Out.
- One odds API call was made by `card.py --cached` (no cache existed in the new container); credits left not seen.

## Next steps
1. After ~3:30 CT: `PYTHONPATH=. python audit/v2_vs_dk.py` (8 early games). If model-over-DK rungs lose money,
   drop that bet type from the props card. Then `python recs.py grade`.
2. Pending today: #160 CLE Under 40.5 (only if Watson starts), #161 LV Under 40.5 (only if Mendoza starts) -
   check starters/inactives (data.gameday_inactives). #162 BAL Under (Mon, only if Huntley starts).
   Teasers #182 CAR+7.5/SF+1.5, #183 SF+1.5/CIN+2.5; spreads #167-173; props/parlays #175-181.
3. NE@DET results: #166, #174, #176, #181 lost.
4. Placed record (recs.py): 3-12, net -$30 before today; ask Chris which of today's he placed (recs.py placed).

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
