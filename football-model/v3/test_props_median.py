"""PROTOCOL amendment 4: average vs median vs player's own hit rate for props. python v3/test_props_median.py"""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import props

N = 8


def with_median(d, stat):
    s = props.project(d, stat)            # proj = EW mean x opp_f, plus _v, opp_f, _n
    g = s.groupby('player_id')._v
    s['med'] = g.transform(lambda v: v.shift().rolling(N, min_periods=3).median())
    s['proj_med'] = s.med * s.opp_f.fillna(1.0)
    s.loc[s._n < 3, 'proj_med'] = np.nan
    hist = g.transform(lambda v: v.shift())   # placeholder to keep index
    s['_hist'] = [None] * len(s)
    vals = {}
    for pid, idx in s.groupby('player_id').indices.items():
        v = s._v.values[idx]
        for j, i in enumerate(idx):
            vals[i] = v[max(0, j - N):j]
    s['_hist'] = [vals[i] for i in range(len(s))] if len(vals) == len(s) else None
    return s


def lines_for(stat, proj):
    if stat == 'anytime_td':
        return [None]
    if stat == 'receptions':
        return [props.half(proj) - 1, props.half(proj), props.half(proj) + 1]
    return [props.half(proj * m) for m in (0.6, 1.0, 1.4)]


def score(s, stat, train, test):
    s = s.reset_index(drop=True)
    pa = props.Pricer(s, stat, train)
    sm = s.copy(); sm['proj'] = sm.proj_med
    pb = props.Pricer(sm, stat, train)
    ev = s[(s.season >= test[0]) & (s.season <= test[1]) & s.proj.notna() & (s.proj > 0) & s.proj_med.notna() & (s.proj_med > 0)]
    A, B, C, Y = [], [], [], []
    for _, r in ev.iterrows():
        h = np.asarray(r._hist, float)
        for L in lines_for(stat, r.proj):
            if L is not None and L < 0.5:
                continue
            a = pa.p_over(r.position, r.proj, L) if L is not None else pa.p_over(r.position, r.proj)
            b = pb.p_over(r.position, r.proj_med, L) if L is not None else pb.p_over(r.position, r.proj_med)
            c = (h > L).mean() if L is not None else (h >= 1).mean()
            y = (r._v > L) if L is not None else (r._v >= 1)
            if np.isnan(a) or np.isnan(b) or len(h) < 3:
                continue
            A.append(a); B.append(b); C.append(c); Y.append(float(y))
    A, B, C, Y = map(np.array, (A, B, C, Y))
    br = lambda p: float(np.mean((p - Y) ** 2))
    return {'n': len(Y), 'average': br(A), 'median': br(B), 'own_hit_rate': br(C)}


if __name__ == '__main__':
    d = props.weekly()
    out, lines = {}, []
    for stat in props.STATS:
        s = with_median(d, stat)
        e = score(s, stat, (2013, 2018), (2019, 2022))
        l = score(s, stat, (2013, 2022), (2023, 2026))
        win = {m: e[m] < e['average'] and l[m] < l['average'] for m in ('median', 'own_hit_rate')}
        out[stat] = {'early': e, 'late': l, 'replaces_average': win}
        lines.append(f"{stat:16s} EARLY(2019-22) n={e['n']:6d} avg {e['average']:.4f} median {e['median']:.4f} hit-rate {e['own_hit_rate']:.4f} | "
                     f"LATE(2023-26) n={l['n']:6d} avg {l['average']:.4f} median {l['median']:.4f} hit-rate {l['own_hit_rate']:.4f} | "
                     f"median wins both: {win['median']}, hit-rate wins both: {win['own_hit_rate']}")
    txt = '\n'.join(lines); print(txt)
    R = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
    json.dump(out, open(os.path.join(R, 'props_median_test.json'), 'w'), indent=1)
    open(os.path.join(R, 'props_median_test.txt'), 'w').write('Brier score, lower = better (PROTOCOL amendment 4)\n' + txt + '\n')
