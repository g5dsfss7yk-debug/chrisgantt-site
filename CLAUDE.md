# Rules from Chris (apply to every session, every answer)

Betting work: football-model/core/HANDOFF.md (the old v3 README is retired). Starting a NEW model? Read football-model/NEW_MODEL_BRIEF.md first.

1. **No guessing, no assuming.** Every number (chance, price, payout, yards, record) must come
   from a tool's output (football-model/core/card_cfb.py, core/card_nfl.py, core/results/*) or a tested result, and say
   which. If no tool or test gives it, say "I don't know" - do not estimate, eyeball, or do
   arithmetic on an assumption. Do not state anything about sportsbooks, other models or
   players as fact unless it was checked in this session, and say how it was checked.
2. **No gut overrides.** Never recommend against a tool's output because it "looks off".
   Only skip a pick for a failed check (inactive player, QB change, NOT VERIFIED item) and name it.
3. **If unsure what Chris means, ask** - do not pick an interpretation and run with it.
4. Plain, short answers. Chris bets $2 per pick on DraftKings (cut from $3, Nov 23); stakes vary (e.g. $5 teaser Nov 27) - log the real stake. Player props: receptions OK (Chris, Nov 15), no rush
   attempts. Prop UNDERS are allowed (Chris, Nov 24: unders happen, just price them correctly). Game-total unders are fine (Chris, Nov 11). Read football-model/core/HANDOFF.md before betting work.
5. **CORE model only (Chris, Nov 28: "There should be no old models picking anything").** v2-v11, run.py and the old
   cards are RETIRED (their scripts exit with a RETIRED message) - never quote them as picks. Everything is in
   football-model/core/ (read core/HANDOFF.md; rules in core/PROTOCOL.md, written before each result; results in
   core/RESULTS.md). Run on GAME DAY only (Chris does not bet early). Every game gets a spread, winner and total pick,
   labelled TESTED PICK or LEAN with its tested record - give picks, do not answer "no bet"; skip only a failed check.
   College card: `python football-model/core/card_cfb.py ESPN_EVENT_ID ...`. NFL card: `core/card_nfl.py` (see HANDOFF).
   TESTED PICKs (core): college spread 2+ pts off the DK line, in-season recalibrated (56.3% / 54.7%); college total
   2+ pts off the DK line, last-3-season median model (53.1% / 57.2%); NFL 6-pt teaser leg on every dog +1.5..+2.5
   (76.5% / 77.1%, needs 73.9%). These passed among many tests (luck is possible) - judge them on the live record.
   Failed in core: college teasers (64-73%), NFL price gap, NFL wind Under, line-free models, player-value model.
   Chris's choices: NFL totals use the original model (leans Over) - he does not want Under-leaning fixes; college
   totals use the median model (about 50/50). Props: core/props_nfl.py - every prop is a LEAN (DK's prices beat the
   model on 119 logged prices); log every DK price Chris sends (Overs and Unders). Chris's placed bets go in
   core/picks/bets.csv with the real stake and DK slip; card picks in core/picks/log.csv.
6. **Pre-bet checks - built into the tools, never skipped, carried into ANY rebuild (Chris has asked for these repeatedly).**
   Before any pick or prop, the tool output must show: (a) ESPN injury list - players Out/Doubtful/IR get NO prop and no
   parlay leg; Questionable = NOT VERIFIED; (b) starting QB checked against ESPN (Out/IR -> NOT VERIFIED); (c) teammates
   Out -> flag the players who inherit targets/carries (NOT VERIFIED); (d) line or total moved 2+ since the opener ->
   CHANGE line; (g) ROLE CHECK - projection far from this season's per-game numbers, or player often gets
   no target/carry -> NOT VERIFIED (card.role_check); (e) weather: gusts 15+ mph or rain chance 50%+ -> flagged; SEVERE WEATHER (Open-Meteo hourly forecast, kickoff+3h: heavy rain 0.30+ in, snow, gusts 30+, freezing wet) and any bad weather -> passing yds, receiving yds AND receptions OVERS are NOT VERIFIED (Chris, Nov 26 - he was right about KC@BUF; never put those Overs in a parlay in bad weather); (h) Chris's game-day observations (weather, injuries, how teams are playing) are a check: any pick they contradict is NOT VERIFIED - do not argue them away with averages; (i) BACKUP QB (<4 starts in the data) -> that game's spread/total and the team's passing/receiving props NOT VERIFIED; (j) TOO GOOD TO BE TRUE - prop chance 15+ pts above DK's break-even -> NOT VERIFIED (DK likely knows something); (k) BET CAP - at most 3 bets per game, never two parlay legs from the same team (Chris, Nov 26: PHI@DAL had 9 picks, went 1-8); (f) re-run ~90 min before kickoff when
   inactives post. If a tool does not show a check, run it by hand from ESPN and say so - never give the pick without it.
   College: no free injury/lineup data exists - the card says so and the starting QB must be checked by hand. A new model/tool is not done until it does (a)-(f). Every prop or pick in an answer comes from a tool run in THIS turn.
7. **Lessons Chris had to point out (Nov 27-28) - check these yourself, every time, before he has to.**
   (a) When a model is replaced, retire the old code AND every scheduled task that runs it, the same day.
   (b) Look at every card and test like a bettor: what share are Overs/Unders, favorites/dogs, home/away? Anything
       past 65% one way is a bias - say so first, before the picks. Chris does not want Under-leaning fixes.
   (c) The league changes (free agency, trades, rule changes): always show results season by season and for the
       last 3 seasons, not only one long block; ask whether old seasons still apply.
   (d) Before giving final picks, ask Chris for his game-day read (QB news, weather, how teams look) and log it
       next to the picks in core/picks/log.csv - his reads are graded too.
   (e) Never answer "no bet": give the pick with its label and record; skip only for a failed check, named.
   (f) A result that looks too good is a bug until shown otherwise (the Nov 27 QB "starter" leak) - check how
       every variable is known BEFORE kickoff.
   (g) When Chris questions an approach, test a genuinely different angle (different question or data), not the
       same model with more variables.
