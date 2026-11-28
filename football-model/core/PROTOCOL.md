# core - ONE complete model (college first, then NFL). Written and committed BEFORE any result (Nov 27 2026)

Chris (Nov 27): "I believe this whole model to be broken... take the best of the models and build a new complete
model that does not track back constantly to the old models." Order: college first, then NFL. Scope: games + props.
Carry over: the ideas that passed tests + every pre-bet check, re-tested inside this model. Defense (Chris): takeaway
rate, pass rush, defensive TDs/big plays, and separate pass and run defense - "why would you leave out any variable".

Standalone: everything lives in `core/` (code) and `data/core/` (downloads). Nothing is imported from `v2`..`v11`,
`nflmodel`, `cfbmodel`. Rules follow NEW_MODEL_BRIEF.md: settings chosen on the EARLY period only, the LATE period
checked ONCE, then frozen; judged live only on games it never saw. No hand overrides. Anything added after results
goes in "Amendments" at the bottom, dated, and labelled as found after the fact.

## College - data
- Play-by-play 2014-2026: cfbfastR (sportsdataverse-data GitHub release `cfbfastR_cfb_pbp`), free, no API limit.
- Player stats per play 2014-2026: cfbfastR-data `player_stats` (for props).
- Lines: CollegeFootballData `/lines` (one call per season and season type; free plan, 740 calls left this month).
  Spread is the HOME number (-7 = home favored). History has no spread/total juice: graded at -110 (needs 52.4%).
- Live: ESPN scoreboard/summary - DraftKings spread, total, moneyline (pickcenter), venue, weather forecast.
- Audit first (`core/audit_cfb.py`): missing values by season, sign of spread vs result, duplicate games.

## College - team ratings (walk-forward: a game uses only games played before its week)
Plays used: scrimmage plays (rush or pass, sacks included) while the offense's win chance is 5%-95% (garbage time out).
Every stat is measured on the offense's plays in that game, so each team gets an OFFENSE number (what it does) and
a DEFENSE number (what it lets offenses do / makes offenses do):
| stat | per | why |
|---|---|---|
| pass EPA | dropback | pass offense / pass defense (separate - Chris) |
| rush EPA | rush | run offense / run defense (separate - Chris) |
| success rate | play | consistency |
| turnovers | game | offense giveaways / DEFENSE TAKEAWAY RATE (Chris) |
| sack rate | dropback | PASS RUSH (Chris). Pressures are not in free college data - not available. |
| explosive plays (20+ yds) | play | BIG PLAYS allowed (Chris) |
| return TDs (INT/fumble returned for TD) | game | DEFENSIVE TDs (Chris) |
| plays | game | pace (totals) |
Opponent adjustment: for each stat, ridge regression stat ~ offense team + defense team + home (penalty 5), each game
weighted 0.5^(games ago / H) counting back from the week being predicted, last two seasons only. FCS teams are rated
like any team. The ONLY tuned setting: H in {4, 8, 16} games, chosen on EARLY-period error (below).

## College - game model
For each game, matchup terms per stat s: home expected = home OFF_s + away DEF_s; away expected = away OFF_s + home DEF_s.
- MARGIN (home points minus away): OLS on [closing spread, neutral-site flag, and (home expected - away expected) for
  every stat]. TOTAL: OLS on [closing total, and (home expected + away expected) for every stat].
- All 8 stats go in (Chris: no variable left out). No variable selection; weights are printed.
- Walk-forward: season S is predicted from a fit on 2015..S-1 (2014 is rating warm-up). EARLY 2017-2022, LATE 2023-2026.
- Choosing H: the H with the lowest EARLY mean squared error of margin + total; then LATE is run once with that H.
- Winner: chance = normal(predicted margin, residual SD from the fit); value vs DK moneyline where history has one.

## College - bets and pass rule (fixed now)
Lines: EARLY = median of listed books' closing line; LATE = DraftKings closing line only (games without one are not bets).
Bet types: spread all games / edge 2+ / edge 4+; total all games / edge 2+ / edge 4+ (edge = |model - line| pts);
winner where the model chance beats the DK moneyline's break-even by 3+ pts.
- TESTED PICK: both periods >= 52.4% at -110 (winner: positive ROI at the listed moneyline), combined one-sided
  binomial p < 0.05 against 52.4%, 100+ bets in each period. Else LEAN. Every game still gets all three picks.
- Carry-over re-tested here: "college spread edge 2+ vs the game-day line" (old v2 result 55.2% / 54.3%) is the
  edge 2+ test above. Weather Under, teasers and price gap were NFL tests - for college they are NOT tested picks.
- Known bias check (old flaw: total leans were mostly Overs): the share of Over picks is printed for each period.

## College - props (after the game model)
Stats: passing yards, rushing yards, receiving yards, receptions, anytime TD. Projection = player's exponentially
weighted per-game average (same H) x the opponent defense factor for that stat type (pass EPA / rush EPA rating,
fit on EARLY). Chance of Over/Under from the spread of (actual / projection) seen in EARLY, by stat.
Test (no DK college prop history exists - so NOT tested against DK): calibration on LATE - predicted vs actual hit
rate in 10 bins, worst gap <= 5 pts = "calibrated", else "NOT calibrated". Every college prop is a LEAN.

## College - checks the card prints (CLAUDE.md rule 6), never skipped
(a) Injuries: ESPN has NO college injury lists (checked Nov 27: 0 of 25 games) -> every pick/prop prints
    "no college injury list - check by hand" and props are NOT VERIFIED until Chris confirms the player is playing.
(b) QB: starter = most pass attempts in the team's last game; if he differs from the team's main QB this season ->
    QB CHANGE, NOT VERIFIED. (i) BACKUP QB: fewer than 4 starts in the data -> spread/total and passing props NOT VERIFIED.
(c) Teammates: a receiver or RB who missed the team's last game (no stats) -> teammates' props flagged.
(d) Line or total moved 2+ since the opener -> CHANGE. (e) Weather (ESPN forecast, outdoor only): gusts 15+ or rain
    chance 50%+ -> flagged; bad weather -> passing yds, receiving yds, receptions OVERS NOT VERIFIED.
(f) Re-run ~90 min before kickoff. (g) Role check: projection far from this season's per-game numbers -> NOT VERIFIED.
(j) Prop chance 15+ pts above DK break-even -> NOT VERIFIED. (k) Max 3 bets per game, no two parlay legs from one team.
Log: `core/picks/log.csv` (every printed pick). Scoreboard: `core/scoreboard.py` (live record next to tested record).

## NFL (second) - written into this file before any NFL result, same structure
NFL protocol is added here as an amendment BEFORE any NFL result, with the same rules (all defense variables,
early/late periods, freeze, checks a-k).

## Amendments
1. (Nov 27, BEFORE any result - implementation details, nothing run yet.) (a) "Games ago" for the rating weights =
   weekly slates ago (one slate per regular-season week; all bowls/playoffs = one slate per season). (b) Fumble-return
   TDs are flagged neither pass nor rush in cfbfastR and only 8% are flagged turnover (audit, 2023): they are counted as
   offense plays, as turnovers and as return TDs. (c) Winner p-value = one-sided t-test that the mean profit per $1
   bet is above 0 (both periods combined). (d) The game fit uses the median closing line in every season (more games);
   bets in LATE are still graded only at the DraftKings line. (e) cfbfastR 2026 play-by-play currently ends at week 12;
   the live card prints the last week its ratings include.
2. (Nov 27, Chris: "this model isn't just based on defense" -> add everything else. Written BEFORE any result with
   these variables. NOTE: LATE 2023-26 was already looked at once (amendment-free run above), so a pass here is
   weaker evidence than a first look; the live scoreboard is the clean test.)
   Added to the college game model, on top of the 8 stats (H stays 4, chosen on EARLY):
   - QB (play-by-play passer names, 2014+): starter = most dropbacks for the team in that game. qb_value = his
     dropback EPA in all EARLIER games, shrunk: sum / (dropbacks + 200). backup_qb = 1 if fewer than 4 earlier starts.
     qb_change = 1 if the starter differs from the team's previous game.
   - Elo: CFBD pregame Elo for each team (in the play-by-play).
   - Talent: CFBD team talent composite for the season (missing - mostly FCS - = that season's lowest value).
   - Returning production: CFBD percent of last season's PPA returning, faded out by week 6:
     value x max(0, 1 - (week - 1) / 5) (missing = season mean).
   - Rest: days since the team's previous game, capped at 14.
   - Travel: miles (/1000) from the team's home stadium to the game venue (CFBD venues + team locations).
   Every variable enters MARGIN as home minus away and TOTAL as home plus away. Nothing is selected or dropped.
   Weather: history is not available today (Open-Meteo archive rate-limited; CFBD weather is a paid feature) - it is
   added later in its own amendment, before its result. Injuries: no free college data - not possible.
   Same bets, same pass rule, results printed next to the first run (8 stats only) on the same games.
3. (Nov 27, BEFORE any amendment-2 result - fill rules found in the data check.) CFBD pregame Elo is complete for
   FBS-vs-FBS games but missing for ~85-99% of games with an FCS team. Missing Elo = the team's most recent earlier
   Elo; if none, the lowest Elo seen that season. Talent starts in 2015 (2014 is warm-up only). Rest: first game of a
   season = 14. Travel: team or venue without coordinates = 0. QB with no earlier dropbacks: qb_value 0, backup_qb 1.
4. (Nov 27, BEFORE any amendment-2 result.) CFBD percent-returning has impossible values (UMass 2021 -3.1, New Mexico
   State 2021 1.7: ratios to a near-zero 2020 total). Clipped to 0..1 before the fade. Travel extremes checked: real
   overseas games (Stanford-Rice and Cal-Hawai'i in Sydney). Talent is missing for the 2014 warm-up season only.
5. (Nov 27, FOUND AFTER the amendment-2 result.) Leak: "starter = most dropbacks in that game" uses in-game
   information (a starter hurt early is recorded as a backup start, which the closing line did not know). The
   amendment-2 TESTED PICK labels are withdrawn until re-run. Fix: starter = the QB on the team's FIRST dropback of the
   game (known at kickoff). Everything else unchanged. The re-run decides; both runs stay in RESULTS.md.
6. (Nov 27, NFL - written BEFORE any NFL result. Chris: "Build the NFL model next".)
   Data (nflverse GitHub releases, free): schedules (scores, closing spread/total with juice, moneylines, roof, temp,
   wind, rest, division), play-by-play 2006-2026, injury reports 2009-2026, depth charts 2009-2026, weekly player stats.
   Own copies in data/core/nfl/. Lines in history are nflverse closing lines (not DraftKings - no DK history exists);
   graded at the listed juice where present, else -110. Live: ESPN DraftKings line, injuries, weather.
   NOTE: every NFL season has already been used by the old builds (v3-v11 used 2006-26) - there is no unseen NFL
   period. Rules are fixed here anyway; the live scoreboard is the only clean test.
   Periods: ratings warm up 2006-08; game-model fit from 2009 (first injury season); EARLY 2011-2017, LATE 2018-2026.
   Same 8 opponent-adjusted stats as college (pass EPA/dropback, rush EPA/rush, success, turnovers incl. fumbles lost
   and interceptions, sack rate, explosive 20+ yd plays, defensive return TDs, plays), win chance 5-95%, ridge
   penalty 5, last two seasons, H in {4, 8, 16} chosen on EARLY error.
   Plus: QB (first-dropback starter; qb_value = earlier dropback EPA / (n + 200); backup < 4 earlier starts; change
   vs previous game); INJURIES: starters = rank-1 players on the team's depth chart from its PREVIOUS week (2025-26
   format: latest snapshot 6+ days before kickoff); counts of offensive non-QB starters and defensive starters listed
   Out/Doubtful (or IR) on that week's injury report, and counts listed Questionable; rest days (nflverse, cap 14);
   division game; weather (outdoor/open only, game book): wind over 10 mph, degrees below 40 F, rain/snow in the
   weather text, dome flag. Margin = home minus away; total = home plus away. Nothing selected or dropped.
   Elo: not in nflverse - not used (the 8-stat ratings are the team strength). Travel: not used (no free stadium
   coordinates without the rate-limited geocoder) - stated, not hidden.
   Bets and pass rule: same as college (spread/total all, edge 2+, edge 4+; winner 3%+ value; 52.4% both periods,
   p < 0.05, 100+ bets each). Bias check: share of Over picks printed.
   Carry-over tested rules re-tested here with the same data, no model: (T) 6-pt teaser leg on every dog +1.5..+2.5
   (needs 73.9% per leg); (P) price gap - moneyline-implied margin 1+ pt off the spread, take the spread side the
   moneyline favors; (W) total Under when game-book wind is 15+ mph or the weather text has rain/snow. Pass = 52.4%
   (T: 73.9%) both periods, p < 0.05, 100+ each.
   Card checks a-k (CLAUDE.md rule 6) from ESPN on game day; props come after the game model, own amendment.
7. (Nov 27, BEFORE any NFL result - found in the NFL audit, core/results/audit_nfl.txt.)
   (a) nflverse schedules have NO weather text column -> rain/snow cannot be built; dropped from the model and rule W
       becomes "game-book wind 15+ mph" only. Stated, not hidden.
   (b) Game-book wind/temp are missing for many outdoor games (2022 46%, 2023 21%, 2026 76%). A missing value is NOT
       read as calm: wind/cold terms = 0 AND a wx_missing flag (1 per outdoor game without data) enters the total
       model; rule W skips those games. Live: ESPN forecast gust fills wind (gusts run higher than game-book
       sustained wind - that mapping is not tested; the card says so).
   (c) Defensive return TD = return_touchdown on a pass or rush play scored by the defense (td_team = defteam);
       kick/punt return TDs (470 of 1910 flagged) are special teams and not counted.
   (d) Turnovers = interceptions + fumbles lost on the offense's plays.
8. (Nov 27, BEFORE any NFL result.) (a) Game-level variables (wind, cold, wx_missing, dome) go only in the TOTAL
   model; division game goes in both; neutral site in margin. (b) Price-gap rule P converts the no-vig moneyline to
   an implied margin with SD = std(margin - closing spread) over 2006-2010 (before every test period). (c) Games
   not yet played have no QB/injury values from history; the live card fills them from ESPN (listed starter, injury
   report), never from the history defaults.
9. (Nov 27, NFL PROPS - written BEFORE any props result. Chris: "Build the props models". College props follow in
   their own amendment.)
   Stats: passing yards (starting QB = first dropback), rushing yards (RB, QB), receiving yards and receptions (WR, TE,
   RB), anytime TD (rush or receiving TD; RB, WR, TE). No rush attempts (Chris). Data: nflverse weekly stats + snap
   counts 2013-2026 - a player-game counts if he had 1+ offensive snap (so 0-catch games are included, not dropped).
   Eligible: 3+ earlier games in the last two seasons.
   Base = player's exponentially weighted mean of that stat over earlier games (last two seasons), half-life HP in
   {4, 8, 16} games - the only tuned setting, chosen on EARLY log loss.
   Adjustments (all in, nothing selected): actual = base x (b0 + b1 opponent factor + b2 team-total ratio + b3 key
   receivers out + b4 lead RB out + b5 player Questionable + b6 backup QB + b7 wind over 10 + b8 cold below 40 +
   b9 wx_missing + b10 dome). Opponent factor = opponent's weighted stat allowed to that position group / league - 1.
   Team-total ratio = closing implied team total / league average - 1. Key receivers = team's top-2 by earlier target
   share, lead RB = most earlier carries (Out/Doubtful on the injury report, player himself excluded).
   Fit by least squares on EARLY 2014-2019 only, frozen, applied to LATE 2020-2026.
   Chance Over/Under = empirical distribution of actual / prediction in EARLY, by stat and prediction tercile.
   Anytime TD: logistic regression on log(base TD rate + 0.01) and the same adjustments, EARLY only.
   Test (no DK prop history before Nov 2026): test line = the player's mean of his last 8 earlier games rounded to
   x.5 (TD: 0.5). Per stat, LATE: "calibrated" if in 10 bins of predicted chance (bins with 100+ props) actual hit
   rate is within 5 pts of predicted; "beats naive" if Brier score is lower than the naive chance (EARLY share of
   Overs at that same kind of line) in BOTH periods. Every prop stays LEAN (not tested against DK).
   DK check (forward, the only DK test possible): on v8/prices/dk_props.csv graded rows logged before kickoff
   (165 now), Brier of this model vs DK's break-even chance - printed, not a pass (too few; old rule waited for 300).
   Card checks a-k on every prop (ESPN injuries, QB, teammates out, role check, weather, too good to be true, bet cap).
10. (Nov 27, FOUND AFTER the props result - bug.) The test line (last-8 mean rounded down to x.5) can be -0.5 or 0.5
    yards for players with almost no touches (backup QBs, fullbacks); with a near-zero projection the ratio method
    breaks (rushing: predicted 97%, actual 47% in that bin). DraftKings never offers such props. Fix: test lines below
    the smallest line DK offered for that stat in Chris's logged prices are excluded (rushing 1.5, receiving 3.5,
    receptions 1.5; passing and TD unchanged - none affected). The card applies the same floor (no prop priced below
    it). Both runs are kept in RESULTS.md.
11. (Nov 27 ~6:05 PM CT, Chris: "test college teaser legs before the Utah game". Written BEFORE any result.)
    College 6-point teaser legs, no model, spreads only. Four rules, nothing else tried:
    C1 every underdog +6; C2 every favorite +6 (e.g. -10.5 -> -4.5); C3 dogs +1.5..+2.5 (the NFL rule);
    C4 favorites -7.5..-8.5 (teased through 7 and 3). EARLY 2017-22 at the median closing line, LATE 2023-26 at
    DraftKings only; pushes out; pick'em games out. Break-even: 73.9% per leg (2-team, -120; DK's college teaser
    price is not checked by any tool - Chris reads it on the slip). Pass = 73.9%+ both periods, one-sided binomial
    p < 0.05 against 73.9% (both periods together), 100+ legs each. Also printed (information, not a rule): C1/C2
    split by spread size (under 7 / 7-14 / over 14).
12. (Nov 28, Chris: "These model fail will happen all the time if you keep basing of DK lines" -> "yes build the
    line-free version". Written BEFORE any result.)
    LINE-FREE game models, college and NFL: identical to the all-variables models (college: amendments 2-5, leak-free
    QB; NFL: amendments 6-8) but with NO betting line anywhere in the model - no closing spread, total or moneyline
    as an input. The model makes its own margin and total; only the bets are graded against the line (that is what
    pays). Rating memory H in {4, 8, 16} re-chosen on EARLY squared error of the line-free model.
    Bets: spread and total at edge 0+ / 2+ / 4+ / 7+ (7+ added because a line-free model disagrees with the line by
    more); winner where the model chance beats the moneyline break-even by 3+ pts. Same periods, lines and pass rule
    as before (52.4% both periods, p < 0.05, 100+ each). LATE periods were seen before (college once, NFL by every
    old build) - a pass is weaker evidence; the live scoreboard is the clean test. Results printed next to the
    with-line model on the same games.
13. (Nov 28, Chris: "C" = better player data. Written BEFORE any result.) NFL only (college has no injury data).
    Replace "how many starters are out" with "how much value is out". Player value = exponentially weighted per-game
    average over his EARLIER games (last two seasons, half-life 8 games), nflverse weekly stats 2012+:
      offense (RB/WR/TE/FB): receiving EPA + rushing EPA per game;
      defense (DL/LB/DB): sacks + 0.5 QB hits + interceptions + 0.5 passes defended + 0.5 tackles for loss + forced
      fumbles per game (weights fixed here, not fitted);
      offensive line: no individual stats exist - count of depth-chart OL starters out (previous week's chart).
    Team-game variables: off_val_out / def_val_out = sum of values of the team's players listed Out or Doubtful that
    week (matched by player id); off_val_q / def_val_q = same for Questionable; ol_out. QB stays as before.
    Added to the all-variables NFL model (with the line - the most accurate one) as home-minus-away (margin) and
    home-plus-away (total). Because player stats start in 2012: fit from 2013, EARLY 2014-2017, LATE 2018-2026, and the
    model WITHOUT the player values is re-run on exactly the same seasons for the comparison. Same bets (edge 0/2/4/7)
    and pass rule. Also printed: the same with no line (amendment 12). PFR pressure data starts 2018 - not used.
14. (Nov 28, Chris: "fix the over bias in the totals". Written BEFORE any result.) Tested Over shares: college
    65-79%, NFL 56-66%. Two fixes for the TOTAL model only (spreads unchanged), college and NFL with-line
    all-variables models (college H=4 first-dropback QB; NFL H=4):
      M (median): fit the total by median (50th percentile) regression instead of least squares - the pick then
         compares the TYPICAL total to the line, not the average (totals have a long high tail).
      O (offset): the line's weight is fixed at 1 and the model predicts only (total - line) from the other inputs.
    Original (least squares) printed beside. Choice between M and O: higher EARLY all-games total hit rate; LATE run
    once with it. Bias counts as fixed if the LATE Over share is 40-60%. Same bets (edge 0/2/4) and pass rule; a
    total is a TESTED PICK only under the usual rule. The card uses the chosen fix from then on.
15. (Nov 28, Chris's choice after amendment 14: "I don't like the unders, old models picked them a lot and did not
    cover".) NFL totals stay on the ORIGINAL least-squares model (Over share 62%; 49.3% / 50.4%), not the median fix
    (37% Overs on 2018-26; 50.6% / 51.3%). College totals: median fix (50% Overs) unless Chris says otherwise.
16. (Nov 28, Chris: "An 8 year gap from 2018 to 2026... the league has changed a lot... I do not think comparing those
    gaps are reasonable" -> "yes test recent seasons only". Written BEFORE any result.)
    RECENT-ONLY fit: the model weights for season S are fit on seasons S-3..S-1 only (3 seasons, Chris's number - not
    tuned). Everything else as now: NFL with-line all-variables model (H=4; totals original least squares, Chris's
    choice); college with-line all-variables model (H=4, first-dropback QB; totals median, amendment 14).
    Judged on recent seasons only, two periods: NFL 2021-2023 / 2024-2026; college 2020-2022 (median line) /
    2023-2026 (DraftKings). Compared with the current all-seasons fit on exactly the same games. Bets: spread and
    total edge 0/2/4, winner 3%+ value; pass = 52.4%+ both periods, p < 0.05, 100+ each. Season-by-season printed.
17. (Nov 28, AFTER the amendment-16 result - card wiring only.) College card: totals come from the last-3-season,
    median total model; a total 2+ points off the DK line is labelled TESTED PICK with its record (53.1% / 57.2%);
    under 2 points stays LEAN. College spreads and winners stay on the all-seasons fit (recent-only did not improve
    them). NFL stays all-seasons for everything.
