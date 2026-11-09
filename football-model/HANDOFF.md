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

## New this session
- `ODDS_API_KEY` is set in the environment (saved as DDS_API_KEY; code reads both).
  `python run.py odds --team Bills` = DK legs vs sharp-book no-vig price. Not yet run live - test it.
- RB rushing ladders: favored backs no longer shrunk toward 50/50 (they hit 79-80%).
- recs.py grades from ESPN box scores (waits for a game's own summary to say final).

## To do next
1. `python recs.py grade` - recs #6-#11 (GB@NE props, TB@CHI props) were pending.
   Known so far: Stevenson rushing leg lost (32 yds), so #6/#7 lose; #8 Stevenson anytime TD won.
2. Test `run.py odds --team Bills` (Monday night BUF @ MIN; Kyler Murray OUT -> Carson Wentz).
3. Build prop parlays for MNF from legs with a price edge; log them in recs.py.
4. Commit and push to branch claude/football-model.
