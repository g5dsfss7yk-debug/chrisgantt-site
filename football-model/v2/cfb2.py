"""College model v2 (Nov 24 2026 rebuild; the old college model failed: 48.2% vs close).
Same design as the NFL v2: each team carries exponentially weighted play-by-play ratings (garbage
time removed), optionally adjusted for the opponent's strength, pulled toward average at each new
season. A standardized ridge turns home-minus-away ratings + the line into a predicted margin/total.
Graded at ESPN's game-day line (the latest before kickoff). Walk-forward: every season is predicted
by a fit on earlier seasons only.
Rule set BEFORE testing (Chris, Nov 24): use it only if picks beat 52.4% in BOTH 2018-22 and 2023-26;
settings chosen on 2018-22 only.   PYTHONPATH=. python v2/cfb2.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from cfbmodel import data as cd

STATS = ["epa", "sr", "explosive", "havoc", "sack", "giveaways", "st_epa", "plays", "rz"]
HALF_LIFE, CARRY, OPP_ADJ, ALPHA = 8, 0.6, 1.0, 10.0   # chosen on 2018-22 only (Nov 24 run below)
# Nov 24 one-time check (2018-22 / 2023-26, vs ESPN's game-day line): spread all games 50.1% / 52.0% (FAILS),
# edge 1+ 51.1% / 51.2% (FAILS), edge 2+ 55.2% of 507 / 54.3% of 361 (PASSES), edge 3+ 57.8% of 147 / 55.9% of 111.
# Totals fail (edge 2+ 49.7% / 47.9%). So: college SPREAD picks only at edge 2+; no college totals from this model.
EDGE_MIN = 2.0


def load():
    g = cd.load_schedules()
    tg = cd.load_team_games()
    tg["rz"] = tg.rz_tds / tg.rz_trips.where(tg.rz_trips > 0)
    tg = tg.drop_duplicates(["game_id", "team_id"])
    line = tg.drop_duplicates("game_id")[["game_id", "espn_spread", "espn_total"]]
    g = g.merge(line, on="game_id", how="left")
    return g, tg


def ratings(g, tg):
    t = tg.set_index(["game_id", "team_id"])
    a = 1 - 0.5 ** (1 / HALF_LIFE)
    st, season_of, mean, rows = {}, {}, {}, []
    for r in g.sort_values("start").itertuples(index=False):
        rec = {"game_id": r.game_id}
        for side, tm in (("home", r.home_id), ("away", r.away_id)):
            if tm in st and season_of[tm] != r.season:
                st[tm] = {k: (CARRY * v + (1 - CARRY) * mean.get(k, v)) if k != "n" else v for k, v in st[tm].items()}
                season_of[tm] = r.season
            s = st.get(tm, {})
            for k, v in s.items():
                rec[f"{side}_{k}"] = v
            rec[f"{side}_n"] = s.get("n", 0)
        rows.append(rec)
        if pd.isna(r.result) or (r.game_id, r.home_id) not in t.index or (r.game_id, r.away_id) not in t.index:
            continue
        snap = {tm: dict(st.get(tm, {})) for tm in (r.home_id, r.away_id)}
        for tm, op in ((r.home_id, r.away_id), (r.away_id, r.home_id)):
            off, dfn = t.loc[(r.game_id, tm)], t.loc[(r.game_id, op)]
            obs = {f"o_{k}": off[k] for k in STATS} | {f"d_{k}": dfn[k] for k in STATS}
            pf = r.home_points if tm == r.home_id else r.away_points
            pa = r.away_points if tm == r.home_id else r.home_points
            obs |= {"pf": pf, "pa": pa}
            if OPP_ADJ and snap[op].get("n", 0) >= 3:
                mir = {f"o_{k}": f"d_{k}" for k in STATS} | {f"d_{k}": f"o_{k}" for k in STATS} | {"pf": "pa", "pa": "pf"}
                for k, m in mir.items():
                    if m in snap[op] and m in mean and not pd.isna(obs[k]):
                        obs[k] = obs[k] - OPP_ADJ * (snap[op][m] - mean[m])
            s = st.setdefault(tm, {})
            season_of.setdefault(tm, r.season)
            for k, v in obs.items():
                if pd.isna(v):
                    continue
                v = float(v)
                s[k] = v if k not in s else (1 - a) * s[k] + a * v
                mean[k] = v if k not in mean else 0.998 * mean[k] + 0.002 * v
            s["n"] = s.get("n", 0) + 1
    return pd.DataFrame(rows)


def build():
    g, tg = load()
    return g.merge(ratings(g, tg), on="game_id")


def X(d, line, kind):
    f = {}
    for k in STATS + ["pf", "pa"]:
        h, w = d.get(f"home_o_{k}" if k not in ("pf", "pa") else f"home_{k}"), d.get(f"away_o_{k}" if k not in ("pf", "pa") else f"away_{k}")
        if k in ("pf", "pa"):
            f[f"{k}"] = (h - w) if kind == "spread" else (h + w)
            continue
        hd, wd = d[f"home_d_{k}"], d[f"away_d_{k}"]
        if kind == "spread":
            f[f"off_{k}"], f[f"def_{k}"] = h - w, hd - wd
            f[f"m_{k}"] = (h - wd) - (w - hd)
        else:
            f[f"so_{k}"], f[f"sd_{k}"] = h + w, hd + wd
    f["neutral"] = d.neutral_site.astype(float)
    f["conf"] = d.conference_game.astype(float)
    f["line"] = line
    x = pd.DataFrame(f).fillna(0)
    thin = (d[["home_n", "away_n"]].fillna(0).min(axis=1) < 3).astype(float)
    for c in x:
        if c != "line":
            x[c] = x[c] * (1 - 0.5 * thin)
    return x


def fit(tr, kind):
    line = "espn_spread" if kind == "spread" else "espn_total"
    y = tr.result if kind == "spread" else tr.total
    return make_pipeline(StandardScaler(), Ridge(alpha=ALPHA)).fit(X(tr, tr[line], kind), y)


def walk_forward(d, kind, first=2016):
    line = "espn_spread" if kind == "spread" else "espn_total"
    done = d[d.result.notna() & d[line].notna() & (d.season >= 2015)]
    out = []
    for s in range(first, int(d.season.max()) + 1):
        tr, te = done[done.season < s], d[(d.season == s) & d[line].notna()].copy()
        te["pred"] = fit(tr, kind).predict(X(te, te[line], kind))
        out.append(te)
    return pd.concat(out)


def grade(p, kind, edges=(0, 1, 2, 3)):
    line = "espn_spread" if kind == "spread" else "espn_total"
    p = p[p.result.notna()]
    e = p.pred - p[line]; a = (p.result if kind == "spread" else p.total) - p[line]
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=p.index)
    res = {}
    for lo in edges:
        for per, m in (("2018-22", p.season.between(2018, 2022)), ("2023-26", p.season >= 2023)):
            q = w[m & (e.abs() >= lo)].dropna()
            res[(lo, per)] = (q.mean(), len(q))
    return res


if __name__ == "__main__":
    import itertools
    print("Choosing settings on 2018-22 ONLY (spread, all games and edge 2+):")
    best, base = None, None
    import v2.cfb2 as me
    for hl, opp, alpha in itertools.product((4, 8), (0.0, 1.0), (10.0, 100.0)):
        HALF_LIFE, OPP_ADJ, ALPHA = hl, opp, alpha
        d = build(); r = grade(walk_forward(d, "spread"), "spread")
        sc = r[(0, "2018-22")][0] + r[(2, "2018-22")][0]
        print(f"  half-life {hl}, opponent adj {opp:.0f}, ridge {alpha:.0f}: 2018-22 all {r[(0,'2018-22')][0]:.1%}, edge 2+ {r[(2,'2018-22')][0]:.1%} ({r[(2,'2018-22')][1]})", flush=True)
        if best is None or sc > best[0]:
            best = (sc, hl, opp, alpha, d)
    _, HALF_LIFE, OPP_ADJ, ALPHA, d = best
    print(f"\nCHOSEN on 2018-22: half-life {HALF_LIFE}, opponent adj {OPP_ADJ:.0f}, ridge {ALPHA:.0f}. Now the one-time check:")
    for kind in ("spread", "total"):
        r = grade(walk_forward(d, kind), kind)
        print(f"  {kind}: " + " | ".join(f"edge {lo}+ {r[(lo,'2018-22')][0]:.1%} of {r[(lo,'2018-22')][1]} / {r[(lo,'2023-26')][0]:.1%} of {r[(lo,'2023-26')][1]}" for lo in (0, 1, 2, 3)))
