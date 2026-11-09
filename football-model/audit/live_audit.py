"""Audit D: live (in-game) ladder chances. Train 2018-22, test 2023-26, out of sample.
Is P(finish at X+ | stats so far, score, time left) calibrated?"""
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd
from nflmodel import props, statprops, data, live

pre = statprops.prepare(props.build(props.load_player_games(), data.load_games()))
sp = pd.concat([live.splits(s) for s in range(live.FIRST, data.current_season() + 1)], ignore_index=True)
STEP = {"rushing_yards": 10, "receiving_yards": 10, "passing_yards": 25}
out = []
for mk in live.MARKETS:
    rows = live.rows_for(mk, sp, pre)
    rows = rows[rows["games"] >= 1]
    tr, te = rows[rows["season"] <= 2022], rows[rows["season"] >= 2023].copy()
    lm = live.LiveModel(mk).fit(tr)
    te["pred"] = lm.predict(te)
    st = STEP[mk]
    for k in range(1, 7):
        rung = (np.floor(te["cur_yds"] / st) + k) * st
        p = [lm.p_reach(a, c, r) for a, c, r in zip(te["pred"], te["cur_yds"], rung)]
        out.append(pd.DataFrame({"market": mk, "secs": te["secs_left"].values, "p": p,
                                 "hit": (te["final"].values >= rung.values)}))
    print("done", mk, "MAE rest", round((te["pred"] - te["rest"]).abs().mean(), 1), flush=True)
a = pd.concat(out).dropna()
a = a[(a.p > 0.03) & (a.p < 0.97)]
a["bucket"] = pd.cut(a.p, [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1])
print(a.groupby("bucket", observed=True).agg(n=("hit", "size"), predicted=("p", "mean"), actual=("hit", "mean")).round(3).to_string())
print(a.groupby(["market"]).apply(lambda g: pd.Series({"n": len(g), "pred": g.p.mean(), "actual": g.hit.mean(),
      "brier": ((g.p - g.hit) ** 2).mean()})).round(3).to_string())
a["when"] = np.where(a.secs >= 2250, "1st half early", np.where(a.secs >= 1350, "around half", "4th qtr side"))
print(a.groupby(["when", pd.cut(a.p, [0, .3, .5, .7, 1])], observed=True).agg(n=("hit", "size"), pred=("p", "mean"), actual=("hit", "mean")).round(3).to_string())
