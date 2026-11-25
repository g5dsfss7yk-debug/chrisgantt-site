"""Nov 23 2026: two props inputs Chris asked for, tested out of sample (fit 2015-22, test 2023-26).
  VAC    targets/carries freed up by teammates listed Out/Doubtful
  ROBUST share of the last 8/16 games with a TD, and last-8 medians (one big game cannot skew them)
Score = Brier score of the chance of reaching each standard rung (lower is better), and how far the
model's chance was from the real hit rate in two groups that matter: a teammate's work freed up
(4+ targets or carries at the player's position) and players with one big game in their last 8.
    PYTHONPATH=. python v2/test_props_new.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props

RUNGS = {"rushing_yards": [25, 40, 50, 60, 75, 100], "receiving_yards": [25, 40, 50, 60, 75, 100],
         "passing_yards": [175, 200, 225, 250, 275, 300], "receptions": [2, 3, 4, 5, 6, 7],
         "rush_rec_yards": [40, 60, 75, 100, 125], "passing_tds": [1, 2, 3], "anytime_td": [1]}
h = pd.read_pickle(Path(__file__).parent / "props_hist.pkl") if (Path(__file__).parent / "props_hist.pkl").exists() \
    else props.history(props.load().query("season >= 2015"))
g = h.groupby("player_id")
h["big8"] = g["tds"].transform(lambda x: x.shift().rolling(8, min_periods=1).max()) >= 2      # a 2+ TD game in the last 8


def score(vac, rob):
    props.USE_VAC, props.USE_ROBUST = vac, rob
    out = {}
    for mk, rungs in RUNGS.items():
        m = props.StatModel(mk)
        x = m.rows(h)
        m.fit(x[x.season <= 2022])
        te = x[x.season >= 2023]
        pr = m.predict(te)
        rows = []
        for r in rungs:
            p = np.array([m.p_reach(v, r) for v in pr])
            rows.append(pd.DataFrame({"p": p, "hit": (te["y"].values >= r).astype(float),
                                      "vac": (te.vac_t_pos.values >= 4) | (te.vac_c_pos.values >= 4), "big": te.big8.values}))
        t = pd.concat(rows)
        b = lambda q: ((q.p - q.hit) ** 2).mean()
        gap = lambda q: q.hit.mean() - q.p.mean()
        out[mk] = (b(t), b(t[t.vac]), gap(t[t.vac]), int(t.vac.sum()), b(t[t.big]), gap(t[t.big]), int(t.big.sum()))
        print(f"  {mk:16s} Brier all {out[mk][0]:.4f} | teammate out: Brier {out[mk][1]:.4f}, real minus model {out[mk][2]:+.1%} "
              f"(n {out[mk][3]}) | big game in last 8: Brier {out[mk][4]:.4f}, real minus model {out[mk][5]:+.1%} (n {out[mk][6]})", flush=True)
    return out


if __name__ == "__main__":
    res = {}
    for name, vac, rob in (("CURRENT", False, False), ("+ freed-up targets/carries", True, False),
                           ("+ TD-game rate and medians", False, True), ("+ both", True, True)):
        print(f"\n{name}  (fit 2015-22, scored on 2023-26)")
        res[name] = score(vac, rob)
    base = res["CURRENT"]
    print("\nBrier change vs CURRENT (negative = better), all rungs / teammate-out / big-game players:")
    for name, r in res.items():
        if name != "CURRENT":
            print(f"  {name:28s} " + "  ".join(f"{mk[:12]} {r[mk][0]-base[mk][0]:+.4f}/{r[mk][1]-base[mk][1]:+.4f}/{r[mk][4]-base[mk][4]:+.4f}" for mk in RUNGS))
    props.USE_VAC = props.USE_ROBUST = False
