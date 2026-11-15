"""Spread/total model variants, chosen on 2015-22 only, then checked on 2023-26.
Graded the way Chris bets: edge vs DK's game-day line (closing line), graded at that line."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from v2 import nfl

d = nfl.build()
d = d[d.season >= 2009].copy()
d["move"] = (d.spread_line - d.spread_open).fillna(0)


def run(kind, target, line, make, extra=lambda d: {}, alpha=30):
    out = []
    for s in range(2015, int(d.season.max()) + 1):
        tr = d[(d.season < s) & d.result.notna() & d[line].notna()]
        te = d[(d.season == s) & d.result.notna() & d[line].notna()].copy()
        X = lambda x: nfl.X(x, x[line], kind).assign(**extra(x))
        y = target(tr)
        m = make().fit(X(tr), y)
        te["pred"] = m.predict(X(te))
        out.append(te)
    return pd.concat(out)


def grade(p, kind, line, resid):
    edge = p.pred if resid else p.pred - p[line]
    act = (p.result if kind == "spread" else p.total) - p[line]
    w = pd.Series(np.where(act == 0, np.nan, np.sign(act) == np.sign(edge)), index=p.index)
    r = []
    for per in (p.season <= 2022, p.season >= 2023):
        a = w[per].dropna(); top = w[per & (edge.abs() >= edge[per].abs().quantile(0.7))].dropna()
        r.append(f"all {a.mean():.1%} top30% {top.mean():.1%}({len(top)})")
    over = (edge > 0).mean()
    return " | ".join(r) + (f" | picks over/home {over:.0%}")


ridge = lambda a=30: (lambda: Ridge(alpha=a))
gbm = lambda: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=200, min_samples_leaf=80)
V = {
 "A current: margin ~ feats + CLOSE line": ("spread", lambda t: t.result, "spread_line", ridge(), lambda x: {}, False),
 "B residual (margin - close) ~ feats": ("spread", lambda t: t.result - t.spread_line, "spread_line", ridge(), lambda x: {}, True),
 "C residual + line move": ("spread", lambda t: t.result - t.spread_line, "spread_line", ridge(), lambda x: {"move": x.move}, True),
 "D residual, strong shrink a=300": ("spread", lambda t: t.result - t.spread_line, "spread_line", ridge(300), lambda x: {"move": x.move}, True),
 "E residual, boosted trees": ("spread", lambda t: t.result - t.spread_line, "spread_line", gbm, lambda x: {"move": x.move}, True),
 "T1 current totals: total ~ feats + line": ("total", lambda t: t.total, "total_line", ridge(), lambda x: {}, False),
 "T2 totals residual (total - line)": ("total", lambda t: t.total - t.total_line, "total_line", ridge(), lambda x: {}, True),
 "T3 totals residual, last 4 seasons only": ("total", None, "total_line", ridge(), lambda x: {}, True),
}
for name, (kind, tgt, line, make, extra, resid) in V.items():
    if name.startswith("T3"):
        out = []
        for s in range(2015, int(d.season.max()) + 1):
            tr = d[(d.season < s) & (d.season >= s - 4) & d.total.notna()]
            te = d[(d.season == s) & d.total.notna()].copy()
            m = Ridge(alpha=30).fit(nfl.X(tr, tr.total_line, "total"), tr.total - tr.total_line)
            te["pred"] = m.predict(nfl.X(te, te.total_line, "total")); out.append(te)
        p = pd.concat(out)
    else:
        p = run(kind, tgt, line, make, extra)
    print(f"{name:42s} 2015-22: {grade(p, kind, line, resid)}", flush=True)
