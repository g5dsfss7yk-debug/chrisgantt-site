# v10 learning layer - written and committed BEFORE any v10 result (Nov 26 2026, ~10:40 PM CT)

Chris (Nov 26): "We need the model to learn and adjust from its mistakes." First day of DK prices (v8 price log,
113 graded Over props, CHI@DET / PHI@DAL / KC@BUF, looked at once): DK's prices were MORE accurate than the model
(Brier 0.220 vs 0.231); props the model called value (5+ pts over DK) hit 25% vs DK's implied 38%. One day, one
storm game - not a test - but it says: the model should learn from DK's price and from its own misses.

## Method (fixed now)
For each graded, pre-kickoff price in v8/prices/dk_props.csv: y = Over hit (1/0), m = logit(v8 chance if logged,
else v3), k = logit(DK break-even of the Over price). Learned chance = logistic regression y ~ a + b*m + c*k, fit
ONLY on game days BEFORE the day being priced (walk-forward). Refit after every game day (scoreboard runs it).

## Test (runs automatically once 300 graded prices exist; first day is warm-up only)
Walk-forward Brier of learned vs model vs DK over every day after the first 100 graded prices. The learned chance
becomes the main number in `card.py prop` only if its Brier beats BOTH the model and DK's price over 300+ walk-forward
prices. Until then it is printed for information as "learned (not yet proven)". Nothing else is tried.

## Amendments
