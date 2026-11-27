# Rules from Chris (apply to every session, every answer)

Betting work: football-model/v3/README.md. Starting a NEW model? Read football-model/NEW_MODEL_BRIEF.md first.

1. **No guessing, no assuming.** Every number (chance, price, payout, yards, record) must come
   from a tool's output (football-model/v3/card.py, v3/scoreboard.py, v3/results/*) or a tested result, and say
   which. If no tool or test gives it, say "I don't know" - do not estimate, eyeball, or do
   arithmetic on an assumption. Do not state anything about sportsbooks, other models or
   players as fact unless it was checked in this session, and say how it was checked.
2. **No gut overrides.** Never recommend against a tool's output because it "looks off".
   Only skip a pick for a failed check (inactive player, QB change, NOT VERIFIED item) and name it.
3. **If unsure what Chris means, ask** - do not pick an interpretation and run with it.
4. Plain, short answers. Chris bets $2 per pick on DraftKings (cut from $3, Nov 23). Player props: receptions OK (Chris, Nov 15), no rush
   attempts. Prop UNDERS are allowed (Chris, Nov 24: unders happen, just price them correctly). Game-total unders are fine (Chris, Nov 11). Read football-model/v3/HANDOFF.md before betting work.
5. **V3 model, a pick on every game (Chris, Nov 15; v3 built Nov 25).** v2 and the old models are retired (their rule-5 text:
   football-model/v2/RULE5_ARCHIVE.md). Run on GAME DAY only (Chris does not bet early - never quote opening-line records):
   `python football-model/v3/card.py nfl --week N` and `python football-model/v3/card.py cfb --date YYYYMMDD`. Every game gets a
   spread, winner and total pick, labelled TESTED PICK or LEAN with its tested record (EARLY / LATE). Rules were fixed before
   testing (v3/PROTOCOL.md); results in v3/RESULTS.md. The ONLY tested pick: NFL 6-pt teaser leg on every dog +1.5..+2.5
   (75.5% 2006-16 / 77.1% 2017-26; needs 73.9% per leg for a 2-team -120 teaser; margin over break-even not proven, p=0.06;
   DK's teaser price is not checked by a tool - Chris reads it on the slip). Second tested pick (v4, Nov 25, football-model/v4/RESULTS.md):
   NFL `>> PRICE GAP` - DK moneyline implies a margin 1+ pt off the spread: 53.9% / 53.9%, not proven above break-even,
   not a bet when DK's juice needs more than 53.9% (card prints NOT a bet). Price checker (v5, Nov 25, Chris OK'd the Odds API key):
   `python football-model/v5/pricecheck.py nfl --markets spreads,totals,h2h` - DK vs Pinnacle no-vig, VALUE at EV >= +2%; costs 1 credit
   per market (check credits; --cached is free); not backtested on DK - judged on the scoreboard. Third tested pick (v6, Nov 26, football-model/v6/RESULTS.md, Chris asked): `>> WEATHER UNDER` on the card when ESPN's forecast has gusts 25+ (WINDY: 55.9% / 56.7%) or rain chance 50%+ (BAD: 54.9% / 60.5%); tested on kickoff weather, the forecast mapping is not tested. In bad weather passing and receiving yards ran BELOW the props projection (prop tool prints it - treat Overs on those as NOT VERIFIED); rushing yards did NOT run higher. v7 (Nov 26, football-model/v7/RESULTS.md): `card.py prop` also prints tested notes - DK team total 26.5+ -> passing yards Over; 19.5 or less -> passing and receiving yards Under; key receiver out -> teammates' receiving yards/receptions Over; lead RB out -> other RBs' rushing yards Over (all are notes, the v3 chances are unchanged). v8 props (Nov 26, football-model/v8/RESULTS.md, Chris asked): `card.py prop` now shows the v8 chance first (v3 projection x weather / key receiver out / lead RB out / team total, fit 2013-22; beat v3 on every stat in both test periods; receptions now calibrated); v6/v7 prop notes are inside v8. v9 severity (Nov 26, football-model/v9/RESULTS.md, Chris asked): forecast gusts 30+ -> `>> WEATHER UNDER` (55.4% / 59.3%); heavy rain (0.30+ in) -> receiving yards and receptions ran Under; gusts 30+ -> passing yards ran Under; heavy rain did NOT raise rushing yards (they fell too). v11 ONE combined game model (Nov 26, football-model/v11/RESULTS.md, Chris asked): the card's spread/winner/total now come from v11 = v3 + weather severity + backup QB + key players/defensive starters out + props yardage; beat v3 in both periods (spreads 52.5% / 50.8%, totals 49.6% / 52.6%) but still LEAN - not a tested pick. v10 learning layer (football-model/v10): learns model-vs-DK weight from graded prices, printed as 'learned, not yet proven'. Every DK prop price priced goes to football-model/v8/prices/dk_props.csv (the only way to ever test props against DK - log Chris's slip prices). Everything else is LEAN: NFL spreads 50.8% / 50.6%,
   NFL totals 52.2% / 50.5%, college spreads 50.8% / 50.5%, college totals 49.2% / 49.7%. Known flaw: total leans are mostly
   Overs (model compares the mean to the line) - say so when giving a total. Props: `v3/card.py prop "Name" stat line --over P
   --under P` prices Over AND Under; rushing/receiving yards calibrated, passing yards/receptions/TDs not; beating DK prices NOT
   tested, so every prop is a LEAN. The model is FROZEN: no changes except proven bugs; no hand overrides; skip only for a
   failed check (** NOT VERIFIED QB, player Out). Judge it only by `python football-model/v3/scoreboard.py` (live record).
   Log: the card writes v3/picks/log.csv itself.
6. **Pre-bet checks - built into the tools, never skipped, carried into ANY rebuild (Chris has asked for these repeatedly).**
   Before any pick or prop, the tool output must show: (a) ESPN injury list - players Out/Doubtful/IR get NO prop and no
   parlay leg; Questionable = NOT VERIFIED; (b) starting QB checked against ESPN (Out/IR -> NOT VERIFIED); (c) teammates
   Out -> flag the players who inherit targets/carries (NOT VERIFIED); (d) line or total moved 2+ since the opener ->
   CHANGE line; (g) ROLE CHECK - projection far from this season's per-game numbers, or player often gets
   no target/carry -> NOT VERIFIED (card.role_check); (e) weather: gusts 15+ mph or rain chance 50%+ -> flagged; SEVERE WEATHER (Open-Meteo hourly forecast, kickoff+3h: heavy rain 0.30+ in, snow, gusts 30+, freezing wet) and any bad weather -> passing yds, receiving yds AND receptions OVERS are NOT VERIFIED (Chris, Nov 26 - he was right about KC@BUF; never put those Overs in a parlay in bad weather); (h) Chris's game-day observations (weather, injuries, how teams are playing) are a check: any pick they contradict is NOT VERIFIED - do not argue them away with averages; (i) BACKUP QB (<4 starts in the data) -> that game's spread/total and the team's passing/receiving props NOT VERIFIED; (j) TOO GOOD TO BE TRUE - prop chance 15+ pts above DK's break-even -> NOT VERIFIED (DK likely knows something); (k) BET CAP - at most 3 bets per game, never two parlay legs from the same team (Chris, Nov 26: PHI@DAL had 9 picks, went 1-8); (f) re-run ~90 min before kickoff when
   inactives post. If a tool does not show a check, run it by hand from ESPN and say so - never give the pick without it.
   A new model/tool is not done until it does (a)-(f). Every prop or pick in an answer comes from a tool run in THIS turn.
