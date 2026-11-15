# Rules from Chris (apply to every session, every answer)

1. **No guessing, no assuming.** Every number (chance, price, payout, yards, record) must come
   from a tool's output (football-model/run.py, recs.py, audit/*) or a tested result, and say
   which. If no tool or test gives it, say "I don't know" - do not estimate, eyeball, or do
   arithmetic on an assumption. Do not state anything about sportsbooks, other models or
   players as fact unless it was checked in this session, and say how it was checked.
2. **No gut overrides.** Never recommend against a tool's output because it "looks off".
   Only skip a pick for a failed check (inactive player, QB change, NOT VERIFIED item) and name it.
3. **If unsure what Chris means, ask** - do not pick an interpretation and run with it.
4. Plain, short answers. Chris bets $3 per pick on DraftKings. Player props: receptions OK (Chris, Nov 15), no rush
   attempts, no unders (DK prop ladders are overs). Game-total unders are fine (Chris, Nov 11). Read football-model/HANDOFF.md before betting work.
5. **V2 model, a pick on every game (Chris, Nov 15).** The old NFL model is scratched. Use
   `python football-model/v2/card.py` (new model, play-by-play ratings, walk-forward tested): give a
   spread, winner and total pick on EVERY game - no "no bet", no "coin toss". Each pick carries its
   tested record, ALWAYS both periods (2015-22 / 2023-26): game-day spread picks (model fit on and graded at
   the game-day line; re-tested Nov 15 after the wind/scaling fixes, v2/improve.py): all games 52.4% / 50.7%, edge 1+ pts
   52.8% / 55.0%, edge 2+ 57.0% of 214 / 58.1% of 62 (few games, not proven; break-even 52.4%)
   (Chris does NOT bet early - Nov 15: injuries and lineup changes after an early bet leave him stuck
   with a bad pick. Never quote opening-line records or suggest betting early);
   totals all games 53.2% / 51.7%, edge 1+ 55.8% / 50.8% (still picks Over more often: 61% of 2023-26 games);
   teaser legs (2-team -120 needs 73.9%): v2 dog +1..+2.5 69.7% / 77.9%,
   +3..+3.5 76.9% / 70.4%, favorite -3.5..-7.5 teased 70.0% / 74.6%. **Best tested bet (v2/dig.py): teaser leg on EVERY dog
   +1.5..+2.5, no model: 72.7% (1999-2014) / 77.0% / 77.3%; with total <= 44: 75.9% / 77.4% / 78.9%. Card prints BEST TEASER LEG.
   DK's teaser price is not checked by any tool - Chris reads it on the slip (needs 73.9% at -120, 75.2% at -130).**
   Card layout (Chris, Nov 15): keep a pick on every game; mark the tested teaser legs (">> TEASER LEG"); show every
   "** CHANGE" line (QB out/changed per ESPN, line or total moved 2+ since the opener, wind 15+, rain, skill players out).
   Flaws found Nov 15: README "V2 flaws".
   Parlays/teasers are built from these legs. Props + alt spreads/totals: `python football-model/v2/props_card.py --before HH:MM`
   (v2 props model; shows the TESTED 2023-26 hit rate for the model's range vs DK's implied chance;
   whether it beats DK's prices is not tested yet - say so). Skip legs marked ROLE CHECK unless
   checked. Odds API: 500 credits/month, a full props run costs about 11 per game - use --cached. College: `cfb.py card` SITUATIONAL total. Log every pick with `recs.py add ... --prob --dk`.