"""Nov 23 2026 (Chris: weather was not in the props). Kickoff weather (wind, rain, snow, temperature,
dome) added to every props market, fit 2015-22, scored on 2023-26. Brier score (lower = better), and
in bad-weather games how far the model's chance was from the real hit rate (0 = right).
    PYTHONPATH=. python v2/test_props_weather.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props

RUNGS = {"rushing_yards": [25, 40, 50, 60, 75, 100], "receiving_yards": [25, 40, 50, 60, 75, 100],
         "passing_yards": [175, 200, 225, 250, 275, 300], "receptions": [2, 3, 4, 5, 6, 7],
         "rush_rec_yards": [40, 60, 75, 100, 125], "passing_tds": [1, 2, 3], "anytime_td": [1]}
props.USE_WX = True                      # load weather columns once (the switch below decides if the model uses them)
h = props.history(props.load().query("season >= 2015"))
bad = {"rain/snow": (h.wx_rain >= 0.5) | (h.wx_snow >= 0.5), "wind 15+ mph": h.wx_wind >= 15,
       "cold (under 32 F)": (h.wx_temp < 32) & (h.wx_dome == 0)}
print("games in 2023-26 by condition:", {k: int(v[h.season >= 2023].groupby(h.game_id).any().sum()) for k, v in bad.items()})
if __name__ == "__main__":
    res = {}
    for use in (False, True):
        props.USE_WX = use
        print(f"\n{'WITH weather' if use else 'CURRENT (no weather)'}  (fit 2015-22, scored on 2023-26)")
        for mk, rungs in RUNGS.items():
            m = props.StatModel(mk); x = m.rows(h); m.fit(x[x.season <= 2022])
            te = x[x.season >= 2023]; pr = m.predict(te)
            t = pd.concat([pd.DataFrame({"p": [m.p_reach(v, r) for v in pr], "hit": (te.y.values >= r).astype(float),
                                         **{k: v.loc[te.index].values for k, v in bad.items()}}) for r in rungs])
            br = ((t.p - t.hit) ** 2).mean()
            res[(use, mk)] = br
            gaps = " | ".join(f"{k}: real minus model {t[t[k]].hit.mean() - t[t[k]].p.mean():+.1%}" for k in bad)
            print(f"  {mk:16s} Brier {br:.4f}   {gaps}", flush=True)
    print("\nBrier change with weather (negative = better):")
    print("  " + "  ".join(f"{mk} {res[(True, mk)] - res[(False, mk)]:+.4f}" for mk in RUNGS))
    props.USE_WX = False
