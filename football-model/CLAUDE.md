# Rules from Chris (apply to every session, every answer)

1. **No guessing, no assuming.** Every number (chance, price, payout, yards, record) must come
   from a tool's output (football-model/run.py, recs.py, audit/*) or a tested result, and say
   which. If no tool or test gives it, say "I don't know" - do not estimate, eyeball, or do
   arithmetic on an assumption. Do not state anything about sportsbooks, other models or
   players as fact unless it was checked in this session, and say how it was checked.
2. **No gut overrides.** Never recommend against a tool's output because it "looks off".
   Only skip a pick for a failed check (inactive player, QB change, NOT VERIFIED item) and name it.
3. **If unsure what Chris means, ask** - do not pick an interpretation and run with it.
4. Plain, short answers. Chris bets $3 per pick on DraftKings. Player props: no receptions, no rush
   attempts, no unders (DK prop ladders are overs). Game-total unders are fine (Chris, Nov 11). Read football-model/HANDOFF.md before betting work.
5. **Pick mode, tested bets only (Chris, Nov 14).** Give picks only of the kinds that beat closing
   lines out of sample (README "Rebuild test" / "Rule scan"), each with its tested record:
   (a) NFL dog teaser legs +1 to +2.5 (79.4% per leg 2023-26); (b) NFL spread STRONG picks from
   `run.py card` (55.6% vs close 2023-26; HOLD = QB unconfirmed); (c) NFL home-team QB change ->
   Under (54.5% 2023-26, only once the change is confirmed); (d) college SITUATIONAL total 56%+ from
   `cfb.py card` (53.4% 2023-26). Everything else (college spreads/old totals, NFL totals, LEAN,
   pregame props) has no edge - say so if asked. Log every pick with `recs.py add ... --prob --dk`.
