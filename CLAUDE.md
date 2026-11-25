# Rules from Chris (apply to every session, every answer)

1. **No guessing, no assuming.** Every number (chance, price, payout, yards, record) must come
   from a tool's output (football-model/run.py, recs.py, audit/*) or a tested result, and say
   which. If no tool or test gives it, say "I don't know" - do not estimate, eyeball, or do
   arithmetic on an assumption. Do not state anything about sportsbooks, other models or
   players as fact unless it was checked in this session, and say how it was checked.
2. **No gut overrides.** Never recommend against a tool's output because it "looks off".
   Only skip a pick for a failed check (inactive player, QB change, NOT VERIFIED item) and name it.
3. **If unsure what Chris means, ask** - do not pick an interpretation and run with it.
4. Plain, short answers. Chris bets $2 per pick on DraftKings (cut from $3, Nov 23). Player props: receptions OK (Chris, Nov 15), no rush
   attempts, no unders (DK prop ladders are overs). Game-total unders are fine (Chris, Nov 11). Read football-model/HANDOFF.md before betting work.
5. **V2 model, a pick on every game (Chris, Nov 15).** The old NFL model is scratched. Use
   `python football-model/v2/card.py` (new model, play-by-play ratings, walk-forward tested): give a
   spread, winner and total pick on EVERY game - no "no bet", no "coin toss". Each pick carries its
   tested record, ALWAYS both periods (2015-22 / 2023-26): game-day spread picks (model fit on and graded at
   the game-day line; with starting-QB value + red-zone rate + competitive plays only since Nov 23, v2/test_nfl.py): all games 52.6% / 54.4%,
   edge 1+ pts 55.0% of 1046 / 53.1% of 420, edge 2+ 58.2% of 368 / 55.8% of 113 (few games, not proven; break-even 52.4%)
   (Chris does NOT bet early - Nov 15: injuries and lineup changes after an early bet leave him stuck
   with a bad pick. Never quote opening-line records or suggest betting early);
   totals (pass rushers out + rain/snow/cold/turf + scoring-level shift: 50% of the last 2 seasons' miss, Nov 24) all games
   54.0% / 52.1%, edge 1+ 54.8% / 53.4%; 2026 all games 47.9% -> 50.9%, Unders still 47% of picks (v2/test_total_level.py);
   teaser legs (2-team -120 needs 73.9%): v2 dog +1..+2.5 73.2% / 82.7%,
   +3..+3.5 77.9% / 71.2%, favorite -3.5..-7.5 teased 69.4% / 76.4%. **Best tested bet (v2/dig.py): teaser leg on EVERY dog
   +1.5..+2.5, no model: 72.7% (1999-2014) / 77.0% / 77.3%; with total <= 44: 75.9% / 77.4% / 78.9%. Card prints BEST TEASER LEG.
   DK's teaser price is not checked by any tool - Chris reads it on the slip (needs 73.9% at -120, 75.2% at -130).**
   Card layout (Chris, Nov 15): keep a pick on every game; mark the tested teaser legs (">> TEASER LEG"); show every
   "** CHANGE" line (QB out/changed per ESPN, line or total moved 2+ since the opener, wind 15+, rain, skill players out).
   Tested Nov 23 and NOT used (v2/test_three.py, README "Three gaps tested"): opponent-adjusted ratings and special teams split by
   unit - not adopted. Pass rushers Out/Doubtful: added to TOTALS only (Chris, Nov 23); counts 0 until the week's injury report posts.
   Nov 23 (v2/test_four.py): starting QB's own value + red-zone TD rate ADDED to spreads; referee crew and pace/pass rate not adopted.
   Nov 23 (Chris): spreads use COMPETITIVE plays only (win prob 10-90%, EPA capped +/-3; v2/test_methods.py). Totals unchanged.
   Props (Nov 23): targets/carries freed up by teammates Out/Doubtful ADDED (card shows [FREED UP ...]); TD-rate/median
   inputs tested, no gain (README "Props: freed-up targets"). Props chances are hit rates of similar past players, not averages.
   Props weather (Nov 23): wind/rain/snow/temp in the model + bad-weather correction (rain/snow or wind 15+); gusts not testable. Turf ON in props (Nov 23).
   Nov 23 batch (v2/test_game_batch.py, v2/test_props_batch.py): luck, travel/time zones/division/byes, coach/returning starters,
   OL out (game); red-zone/goal-line share, depth of target/CPOE, separation (props) - tested, NOT used.
   Flaws found Nov 15: README "V2 flaws".
   Parlays/teasers are built from these legs. Props + alt spreads/totals: `python football-model/v2/props_card.py --before HH:MM`
   (v2 props model; shows the TESTED 2023-26 hit rate for the model's range vs DK's implied chance;
   whether it beats DK's prices is not tested yet - say so). Skip legs marked ROLE CHECK unless
   checked. Odds API: 500 credits/month, a full props run costs about 11 per game - use --cached. College: `cfb.py card` SITUATIONAL total ONLY. NEVER give a college spread or
   side pick: the college spread model FAILED its test (48.2% vs close, 6,451 games, 2019-26). On Nov 24 one was given
   anyway and Chris lost on it. REBUILT Nov 24 (v2/cfb2.py, rule set before testing): college spread picks ONLY from
   `PYTHONPATH=. python v2/cfb2_card.py --date YYYY-MM-DD` and ONLY at edge 2+ pts (55.2% of 507 / 54.3% of 361, 2018-22 /
   2023-26). Chris (Nov 24): EVERY college game gets a lean - the card prints SPREAD LEAN / WINNER LEAN / TOTAL LEAN, clearly
   marked as untested (spread 50.1% / 52.0%, totals 50.8% / 50.9%); TESTED PICK only at spread edge 2+. Lines: DK via CollegeFootballData. Log every pick with `recs.py add ... --prob --dk`.