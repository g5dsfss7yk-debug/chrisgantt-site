"""Audit A: NFL spread tiers graded vs the opener AND vs the closing line; Audit B: teaser legs by season."""
import numpy as np, pandas as pd
from scipy.stats import binomtest
from nflmodel import model, pipeline
df = pipeline.load()
print("rows", len(df), "seasons", df.season.min(), df.season.max(), flush=True)
p = model.walk_forward(df, lambda: model.spread_market(), range(2015, 2027))
p = p.join(df[["spread_open", "spread_line", "result", "season"]].rename(columns={"season": "s"}), rsuffix="_df")
ag = p[p.agree == p.n_models].copy()
ag["conf"] = np.maximum(ag.p, 1 - ag.p)
ag["side"] = np.where(ag.p >= .5, 1, -1)
def rate(d, line):
    o = np.sign(d.result - d[line]); keep = o != 0
    w = int(((o == d.side) & keep).sum()); n = int(keep.sum())
    pv = binomtest(w, n, 0.5, alternative="greater").pvalue if n else np.nan
    return f"{w}-{n-w} {w/n:.1%} (p={pv:.3f})" if n else "none"
for tier, thr in (("STRONG", .55), ("LEAN+STRONG", .53)):
    t = ag[ag.conf >= thr]
    still = t[np.sign(t.rating - t.spread_line) == t.side]   # model still past the closing line
    for per, (a, b) in {"2015-22": (2015, 2022), "2023-26": (2023, 2026), "2025-26": (2025, 2026)}.items():
        q = t[t.s.between(a, b)]; qs = still[still.s.between(a, b)]
        print(f"{tier:12} {per}: vs OPENER {rate(q,'spread_open')} | vs CLOSE (all) {rate(q,'spread_line')} | vs CLOSE when still past it {rate(qs,'spread_line')}", flush=True)
# teasers
g = df[["season", "result", "spread_line", "spread_open"]].dropna()
rows = []
for s, x in g.groupby("season"):
    r = {"season": s}
    for name, lo, hi in (("dog +1..+2.5", 1, 2.5), ("fav -7.5..-8.5", -8.5, -7.5)):
        # home margin result; spread_line > 0 = home favored. dog line for home = -spread_line
        for side in ("home", "away"):
            pass
        legs = []
        for _, z in x.iterrows():
            for team_line, margin in ((-z.spread_line, z.result), (z.spread_line, -z.result)):
                if lo <= team_line <= hi:
                    legs.append(margin + team_line + 6)
        legs = np.array(legs)
        r[name] = f"{(legs > 0).sum()}/{(legs != 0).sum()} {(legs > 0).sum()/max((legs != 0).sum(),1):.0%}"
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))
for name, lo, hi in (("dog +1..+2.5", 1, 2.5), ("fav -7.5..-8.5", -8.5, -7.5)):
    for per, (a, b) in {"2015-22": (2015, 2022), "2023-26": (2023, 2026)}.items():
        legs = []
        for _, z in g[g.season.between(a, b)].iterrows():
            for team_line, margin in ((-z.spread_line, z.result), (z.spread_line, -z.result)):
                if lo <= team_line <= hi:
                    legs.append(margin + team_line + 6)
        legs = np.array(legs); n = (legs != 0).sum(); w = (legs > 0).sum()
        print(f"teaser {name} {per}: {w}/{n} = {w/n:.1%}  (break-even per leg: 2-team -120 73.9%, 3-team +160 72.7%)")
