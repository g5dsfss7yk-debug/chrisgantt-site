"""Nov 23 2026: receptions flaw. Old way: chance = share of players in the same prediction group
(25 groups) who reached N - the top group mixes 5-catch and 9-catch projections, so high-volume
receivers were under-rated. New way: the player's own projection plus the misses of similar
players (as for yards). Fit 2015-22, scored on 2023-26.
    PYTHONPATH=. python v2/test_receptions.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props

h = pd.read_pickle(Path(__file__).parent / "props_hist.pkl") if (Path(__file__).parent / "props_hist.pkl").exists() \
    else props.history(props.load().query("season >= 2015"))
for mk, rungs, col, lo in (("receptions", [2, 3, 4, 5, 6, 7, 8], "ew_receptions", 7.5),
                           ("passing_tds", [1, 2, 3], "ew_passing_tds", 2.0)):
    for name, resid, near in (("old (25 wide groups)", False, None), ("projection + misses", True, None),
                              ("500 closest projections", False, 500), ("1500 closest projections", False, 1500)):
        props.RESID_COUNTS = {mk} if resid else set()
        props.NEAR = {mk: near} if near else {}
        m = props.StatModel(mk); x = m.rows(h); m.fit(x[x.season <= 2022])
        te = x[x.season >= 2023].copy(); pr = m.predict(te)
        t = pd.concat([pd.DataFrame({"p": [m.p_reach(v, r) for v in pr], "hit": (te.y.values >= r).astype(float),
                                     "hot": te[col].values >= lo, "r": r}) for r in rungs])
        top = t[t.r == rungs[-1]]
        cal = t.groupby(pd.cut(t.p, [0, .2, .4, .6, .8, 1]), observed=True).agg(said=("p", "mean"), hit=("hit", "mean"), n=("p", "size"))
        print(f"\n{mk} - {name}: Brier {((t.p - t.hit) ** 2).mean():.4f}")
        print(f"  high-volume ({col} >= {lo}), {rungs[-1]}+: said {top[top.hot].p.mean():.1%}, hit {top[top.hot].hit.mean():.1%} (n {int(top.hot.sum())})")
        print(f"  high-volume, every rung: said {t[t.hot].p.mean():.1%}, hit {t[t.hot].hit.mean():.1%}")
        print("  " + " | ".join(f"{i}: said {r.said:.0%} hit {r.hit:.0%}" for i, r in cal.iterrows()))
props.RESID_COUNTS, props.NEAR = set(), {"receptions": 500}
