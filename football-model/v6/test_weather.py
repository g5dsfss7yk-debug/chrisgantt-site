"""v6 weather test, rules in v6/PROTOCOL.md (committed first). python v6/test_weather.py"""
import os, re, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'v3'))
import data, props, grade

WET = re.compile(r'\b(rain|raining|showers?|drizzle|snow|snowing|sleet|thunderstorms?|storms?)\b')
NOT_WET = re.compile(r'\b(no (rain|snow)|chance|possible|possibly|ending|ended|stopped|earlier)\b')


def wind(t):
    m = re.search(r'wind:[^0-9]{0,25}?(\d+)', t)   # first number in the "Wind:" field (not "windy ... Temp: 16")
    return int(m.group(1)) if m else np.nan


def gust(t):
    m = re.search(r'gusts?\D{0,10}?(\d+)', t)
    return int(m.group(1)) if m else np.nan


def weather():
    w = pd.read_csv(os.path.join(ROOT, 'data', 'v6', 'weather.csv'))
    w = w[w.roof.isin(['outdoors', 'open'])].copy()
    t = w.weather.fillna('').str.lower()
    w['wet'] = t.apply(lambda s: bool(WET.search(s)) and not NOT_WET.search(s))
    w['wind_mph'] = t.apply(wind); w['gust_mph'] = t.apply(gust)
    w['windy'] = (w.wind_mph >= 15) | (w.gust_mph >= 25)
    w['bad'] = w.wet | w.windy
    w['has_text'] = t.str.len() > 0
    return w


def tot_record(x):
    x = x[x.total != x.total_line]
    win = (x.total < x.total_line).sum(); n = len(x)
    return int(win), int(n)


def totals(w):
    g = data.nfl_games(refresh_hours=999)
    g = g[g.result.notna() & g.total_line.notna()][['game_id', 'season', 'total', 'total_line']]
    m = w.drop(columns=['season']).merge(g, on='game_id')
    out = {}
    for key, col in (('G1 WET', 'wet'), ('G2 WINDY', 'windy'), ('G3 BAD', 'bad'), ('control GOOD', None)):
        sel = m[m[col]] if col else m[~m.bad]
        e = tot_record(sel[sel.season.between(2006, 2016)]); l = tot_record(sel[sel.season.between(2017, 2026)])
        pe, pl = e[0] / e[1], l[0] / l[1]
        p = grade.binom_p_above_half(e[0] + l[0], e[1] + l[1])
        ok = col is not None and pe >= 0.524 and pl >= 0.524 and p < 0.05 and e[1] >= 100 and l[1] >= 100
        out[key] = dict(early=e, late=l, early_pct=pe, late_pct=pl, p=p, passes=bool(ok) if col else None)
    return out, m


def binom_p_above(k, n, p0):
    from math import erf, sqrt   # one-sided P(X >= k), X ~ Bin(n, p0), normal approx with continuity correction
    if n == 0:
        return 1.0
    z = (k - 0.5 - n * p0) / sqrt(n * p0 * (1 - p0))
    return float(0.5 * (1 - erf(z / sqrt(2))))


def prop_test(w, stat, side, train, test):
    d = props.weekly()
    s = props.project(d, stat).reset_index(drop=True)
    pr = props.Pricer(s, stat, train)
    bad = set(w[w.bad].game_id); good = set(w[~w.bad].game_id)
    ev = s[s.season.between(*test) & s.proj.notna() & (s.proj > 0) & (s._n >= 3)]
    res = {}
    for name, ids in (('bad', bad), ('good', good)):
        x = ev[ev.game_id.isin(ids)]
        P, Y = [], []
        for _, r in x.iterrows():
            L = props.half(r.proj)
            if L < 0.5:
                continue
            po = pr.p_over(r.position, r.proj, L)
            if np.isnan(po):
                continue
            P.append(po if side == 'over' else 1 - po)
            Y.append(float(r._v > L) if side == 'over' else float(r._v < L))
        P, Y = np.array(P), np.array(Y)
        res[name] = dict(n=len(Y), actual=float(Y.mean()) if len(Y) else np.nan, predicted=float(P.mean()) if len(Y) else np.nan,
                         hits=int(Y.sum()))
    return res


if __name__ == '__main__':
    w = weather()
    lines = [f"Outdoor/open games with weather text: {int(w.has_text.sum())} of {len(w)}; WET {int(w.wet.sum())}, WINDY {int(w.windy.sum())}, BAD {int(w.bad.sum())}"]
    T, m = totals(w)
    lines.append('\nTOTALS - UNDER at the nflverse closing total, -110 (needs 52.4%), pushes out')
    for k, v in T.items():
        lines.append(f"  {k:12s} EARLY 2006-16 {v['early'][0]}/{v['early'][1]} = {v['early_pct']:.1%} | LATE 2017-26 {v['late'][0]}/{v['late'][1]} = {v['late_pct']:.1%}"
                     f" | combined p={v['p']:.3f} | {'PASS' if v['passes'] else 'control' if v['passes'] is None else 'FAIL'}")
    P = {}
    lines.append('\nPROPS in BAD games - line = v3 projection rounded to x.5; actual vs v3 predicted chance (needs +3.0 pts both periods)')
    for key, stat, side in (('P1', 'passing_yards', 'under'), ('P2', 'rushing_yards', 'over'), ('P3', 'receiving_yards', 'under')):
        e = prop_test(w, stat, side, (2013, 2018), (2019, 2022)); l = prop_test(w, stat, side, (2013, 2022), (2023, 2026))
        ge, gl = e['bad']['actual'] - e['bad']['predicted'], l['bad']['actual'] - l['bad']['predicted']
        n = e['bad']['n'] + l['bad']['n']; k = e['bad']['hits'] + l['bad']['hits']
        p0 = (e['bad']['predicted'] * e['bad']['n'] + l['bad']['predicted'] * l['bad']['n']) / n
        p = binom_p_above(k, n, p0)
        ok = ge >= 0.03 and gl >= 0.03 and e['bad']['n'] >= 100 and l['bad']['n'] >= 100 and p < 0.05
        P[key] = dict(stat=stat, side=side, early=e, late=l, gap_early=ge, gap_late=gl, p=p, passes=bool(ok))
        lines.append(f"  {key} {stat} {side.upper():5s} BAD: EARLY n={e['bad']['n']} actual {e['bad']['actual']:.1%} vs model {e['bad']['predicted']:.1%} ({ge*100:+.1f}) | "
                     f"LATE n={l['bad']['n']} actual {l['bad']['actual']:.1%} vs model {l['bad']['predicted']:.1%} ({gl*100:+.1f}) | p={p:.3f} | {'PASS' if ok else 'FAIL'}")
        lines.append(f"     control GOOD: EARLY actual {e['good']['actual']:.1%} vs {e['good']['predicted']:.1%} | LATE actual {l['good']['actual']:.1%} vs {l['good']['predicted']:.1%}")
    txt = '\n'.join(lines); print(txt)
    R = os.path.join(HERE, 'results'); os.makedirs(R, exist_ok=True)
    open(os.path.join(R, 'weather_test.txt'), 'w').write('v6 weather test (v6/PROTOCOL.md)\n' + txt + '\n')
    json.dump({'totals': T, 'props': P}, open(os.path.join(R, 'weather_test.json'), 'w'), indent=1, default=float)
