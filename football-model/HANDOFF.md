# Handoff (Nov 9 2026)

Chris bets $3 per pick on DraftKings for fun: prop parlays and teasers. Wants plain, short answers.

## Ground rules
- Before any pick: QB (incl. Out/Doubtful -> backup), injuries, weather (forecast + ESPN, rain flag),
  surface, form. The cards and `run.py props` print these; read the NOT VERIFIED list.
- Chris's DK has NO receptions, NO rush attempts, NO unders. Prop legs = yards / TDs / passing "X+" ladders.
- Only call a bet "backed" if it is one of these (audit vs closing lines, README "Betting rules"):
  1. 6-pt teaser legs on NFL underdogs +1 to +2.5 (79% in 2023-26; needs ~74%)
  2. Model spreads vs your line (55-56% vs close; small edge)
  3. Prop ladder legs only when the model or sharp books beat DK's price by 3%+
- Everything else is "fun only". College has no proven edge (30-41 live). Favorite teasers are dead.
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
