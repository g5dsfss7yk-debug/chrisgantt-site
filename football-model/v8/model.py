"""v8 props model (rules: v8/PROTOCOL.md, committed first). Test: python v8/model.py test
proj8 = proj3 x f(team implied total, bad weather, key receiver out, lead RB out), f fit by OLS on training seasons."""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
for p in ('v3', 'v6', 'v7'):
    sys.path.insert(0, os.path.join(ROOT, p))
import props

X = ['itt', 'bad', 'rec_out', 'rb_out']
STATS = ['passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'anytime_td']


def features():
    """Context per (game_id, team, player): itt, bad, rec_out/rb_out key sets. Cached to data/v8/context.pkl."""
    cp = os.path.join(ROOT, 'data', 'v8', 'context.pkl')
    if os.path.exists(cp):
        return pd.read_pickle(cp)
    import test_v7 as v7, test_weather as v6
    g = v7.games(); tg = v7.team_games(g); sn = v7.snaps(); d = props.weekly()
    w = v6.weather()
    rec, rb = v7.key_out(tg, d, sn)
    ctx = dict(itt=tg.set_index(['game_id', 'team']).itt, bad=w.set_index('game_id').bad, rec=rec, rb=rb)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    pd.to_pickle(ctx, cp)
    return ctx


def add_x(s, ctx):
    s = s.copy()
    s['nm'] = s.player_display_name.map(lambda n: __import__('test_v7').norm(n))
    s['itt'] = [ctx['itt'].get((a, b), np.nan) for a, b in zip(s.game_id, s.team)]
    s['itt'] = (s.itt - 22).fillna(0.0)
    s['bad'] = s.game_id.map(ctx['bad']).fillna(False).astype(float)
    rk = {}
    for a, b, n in ctx['rec']:
        rk.setdefault((a, b), set()).add(n)
    bk = {}
    for a, b, n in ctx['rb']:
        bk.setdefault((a, b), set()).add(n)
    key = list(zip(s.game_id, s.team))
    s['rec_out'] = [float(k in rk and nm not in rk[k] and pos in ('WR', 'TE')) for k, nm, pos in zip(key, s.nm, s.position)]
    s['rb_out'] = [float(k in bk and nm not in bk[k] and pos == 'RB') for k, nm, pos in zip(key, s.nm, s.position)]
    return s


def fit(s, train):
    t = s[s.season.between(*train) & s.proj.notna() & (s.proj > 0)]
    y = np.clip(t._v / t.proj, 0, 5).values
    A = np.column_stack([np.ones(len(t))] + [t[c].values for c in X])
    b, *_ = np.linalg.lstsq(A, y, rcond=None)
    return b


def apply(s, b):
    A = np.column_stack([np.ones(len(s))] + [s[c].values for c in X])
    return s.proj * np.clip(A @ b, 0.5, 1.5)


def lines(stat, p3):
    if stat == 'anytime_td':
        return [None]
    if stat == 'receptions':
        return [props.half(p3) - 1, props.half(p3), props.half(p3) + 1]
    return [props.half(p3 * m) for m in (0.6, 1.0, 1.4)]


def score(s, stat, train, test):
    b = fit(s, train)
    s8 = s.copy(); s8['proj'] = apply(s, b)
    p3, p8 = props.Pricer(s, stat, train), props.Pricer(s8, stat, train)
    ev = s[s.season.between(*test) & s.proj.notna() & (s.proj > 0)].index
    A, B, Y = [], [], []
    for i in ev:
        r, r8 = s.loc[i], s8.loc[i]
        for L in lines(stat, r.proj):
            if L is not None and L < 0.5:
                continue
            a = p3.p_over(r.position, r.proj, L) if L is not None else p3.p_over(r.position, r.proj)
            c = p8.p_over(r.position, r8.proj, L) if L is not None else p8.p_over(r.position, r8.proj)
            if np.isnan(a) or np.isnan(c):
                continue
            A.append(a); B.append(c); Y.append(float(r._v > L) if L is not None else float(r._v >= 1))
    A, B, Y = map(np.array, (A, B, Y))
    br = lambda p: float(np.mean((p - Y) ** 2))
    dec = np.minimum((B * 10).astype(int), 9)
    tab = pd.DataFrame({'d': dec, 'p': B, 'y': Y}).groupby('d').agg(pred=('p', 'mean'), hit=('y', 'mean'), n=('y', 'size'))
    tab = tab[tab.n >= 50]
    return dict(n=len(Y), brier_v3=br(A), brier_v8=br(B), coef=dict(zip(['const'] + X, map(float, b))),
                worst_gap_v8=float((tab.hit - tab.pred).abs().max()))


if __name__ == '__main__':
    ctx = features(); print('context ready', flush=True)
    d = props.weekly()
    out, txt = {}, []
    for stat in STATS:
        s = add_x(props.project(d, stat).reset_index(drop=True), ctx)
        e = score(s, stat, (2013, 2018), (2019, 2022)); l = score(s, stat, (2013, 2022), (2023, 2026))
        win = e['brier_v8'] < e['brier_v3'] and l['brier_v8'] < l['brier_v3']
        cal = l['worst_gap_v8'] <= 0.03
        out[stat] = dict(early=e, late=l, replaces_v3=bool(win), calibrated=bool(cal))
        txt.append(f"{stat:16s} EARLY n={e['n']:6d} v3 {e['brier_v3']:.5f} v8 {e['brier_v8']:.5f} | LATE n={l['n']:6d} v3 {l['brier_v3']:.5f} "
                   f"v8 {l['brier_v8']:.5f} | v8 wins both: {win} | v8 worst decile gap 2023-26 {l['worst_gap_v8']:.1%} "
                   f"({'calibrated' if cal else 'NOT calibrated'}) | late coef {', '.join(f'{k} {v:+.3f}' for k, v in l['coef'].items())}")
        print(txt[-1], flush=True)
    R = os.path.join(HERE, 'results'); os.makedirs(R, exist_ok=True)
    open(os.path.join(R, 'v8_test.txt'), 'w').write('v8 props model test (Brier, lower = better)\n' + '\n'.join(txt) + '\n')
    json.dump(out, open(os.path.join(R, 'v8_test.json'), 'w'), indent=1)
