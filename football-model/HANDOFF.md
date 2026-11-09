# Handoff (Nov 9 2026)

Chris bets $1-3 on DraftKings for fun: prop parlays and teasers. Wants plain, short answers.

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

## To do next
1. `python recs.py grade` - #9-#13 pending.
2. When model and sharp books disagree a lot (Jones: model 54 yds, market 33.5), check role/usage news.
