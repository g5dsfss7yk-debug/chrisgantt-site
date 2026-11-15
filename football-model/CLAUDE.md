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
   tested record: spread edge 1+ pts 55.0% of 333 (2023-26 vs opener), edge under 1 51.3%; totals
   51.2%; teaser legs v2 dog +1..+2.5 teased 6 79.3% per leg, +3..+3.5 72.8% (2-team -120 needs 73.9%).
   Parlays/teasers are built from these legs. Props + alt spreads/totals: `python football-model/v2/props_card.py --before HH:MM`
   (v2 props model; shows the TESTED 2023-26 hit rate for the model's range vs DK's implied chance;
   whether it beats DK's prices is not tested yet - say so). Skip legs marked ROLE CHECK unless
   checked. Odds API: 500 credits/month, a full props run costs about 11 per game - use --cached. College: `cfb.py card` SITUATIONAL total. Log every pick with `recs.py add ... --prob --dk`.