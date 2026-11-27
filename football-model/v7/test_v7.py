"""v7 overlooked-variables test, rules in v7/PROTOCOL.md (committed first). python v7/test_v7.py"""
import os, re, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'v3')); sys.path.insert(0, os.path.join(ROOT, 'v6'))
import data, props, grade
import test_weather as v6

DB = {'CB', 'S', 'FS', 'SS', 'DB', 'SAF'}


def norm(n):
    n = re.sub(r'[^a-z ]', '', str(n).lower())
    return ' '.join(re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', n).split())


def games():
    g = data.nfl_games(refresh_hours=999)
    g = g[g.result.notna() & g.total_line.notna() & g.spread_line.notna()].copy()
    return g


def team_games(g):
    """One row per team-game with ITT, spread from the team's side (+ = team favored), and order within season."""
    h = pd.DataFrame({'game_id': g.game_id, 'season': g.season, 'week': g.week, 'team': g.home_team,
                      'fav': g.spread_line, 'itt': (g.total_line + g.spread_line) / 2})
    a = pd.DataFrame({'game_id': g.game_id, 'season': g.season, 'week': g.week, 'team': g.away_team,
                      'fav': -g.spread_line, 'itt': (g.total_line - g.spread_line) / 2})
    t = pd.concat([h, a], ignore_index=True).sort_values(['team', 'season', 'week']).reset_index(drop=True)
    t['k'] = t.groupby(['team', 'season']).cumcount()
    return t


def snaps():
    d = os.path.join(ROOT, 'data', 'v3', 'stats')
    s = pd.concat([pd.read_parquet(os.path.join(d, f'snaps_{y}.parquet')) for y in range(2012, 2027)], ignore_index=True)
    s['nm'] = s.player.map(norm)
    return s[['game_id', 'season', 'week', 'nm', 'position', 'team', 'offense_snaps', 'defense_pct']]


def def_out(tg, sn):
    """Per (game_id, team): defensive starters out, DB starters out (PROTOCOL C)."""
    by = {k: v for k, v in sn[sn.defense_pct > 0].groupby(['game_id', 'team'])}
    have = set(sn.game_id)
    rows = []
    for (team, season), x in tg.groupby(['team', 'season']):
        ids = list(x.sort_values('k').game_id)
        for k, gid in enumerate(ids):
            if k < 3 or gid not in have:
                continue
            prev = [by.get((p, team)) for p in ids[k - 3:k]]
            if any(p is None for p in prev):
                continue
            pp = pd.concat(prev)
            agg = pp.groupby('nm').agg(n=('defense_pct', 'size'), pct=('defense_pct', 'mean'), pos=('position', 'last'))
            st = agg[(agg.n >= 2) & (agg.pct >= 0.60)]
            now = by.get((gid, team))
            played = set(now.nm) if now is not None else set()
            out = st[~st.index.isin(played)]
            rows.append(dict(game_id=gid, team=team, d_out=len(out), db_out=int(out.pos.isin(DB).sum())))
    return pd.DataFrame(rows)


def key_out(tg, d, sn):
    """Per (game_id, team): key receiver out (B1/B2), key RB out (B3). Returns dict of sets of (game_id, team, out_name)."""
    offp = {k: set(v.nm) for k, v in sn[sn.offense_snaps > 0].groupby(['game_id', 'team'])}
    have = set(sn.game_id)
    w = d[['player_display_name', 'position', 'team', 'game_id', 'season', 'targets', 'carries']].copy()
    w['nm'] = w.player_display_name.map(norm)
    tt = w.groupby(['game_id', 'team'])[['targets', 'carries']].sum().rename(columns={'targets': 'tt', 'carries': 'tc'})
    w = w.join(tt, on=['game_id', 'team'])
    wg = {k: v for k, v in w.groupby(['game_id', 'team'])}
    rec, rb = set(), set()
    for (team, season), x in tg.groupby(['team', 'season']):
        ids = list(x.sort_values('k').game_id)
        for k, gid in enumerate(ids):
            if k < 2 or gid not in have or (gid, team) not in offp:
                continue
            played_now = offp[(gid, team)]
            prev2 = [offp.get((p, team), set()) for p in ids[max(0, k - 2):k]]
            hist = [wg[(p, team)] for p in ids[:k] if (p, team) in wg]
            if not hist:
                continue
            H = pd.concat(hist)
            for nm, ph in H[H.position.isin(['WR', 'TE', 'RB'])].groupby('nm'):
                if nm in played_now or not any(nm in s_ for s_ in prev2):
                    continue
                last = ph.tail(3)
                ts = last.targets.sum() / max(last.tt.sum(), 1)
                cs = last.carries.sum() / max(last.tc.sum(), 1)
                if ts >= 0.18:
                    rec.add((gid, team, nm))
                if ph.position.iloc[-1] == 'RB' and cs >= 0.50:
                    rb.add((gid, team, nm))
    return rec, rb


def binom_p_above(k, n, p0):
    from math import erf, sqrt
    if n == 0:
        return 1.0
    z = (k - 0.5 - n * p0) / sqrt(n * p0 * (1 - p0))
    return float(0.5 * (1 - erf(z / sqrt(2))))


_EVAL = {}


def evals(d, stat):
    """v3 projection rows 2019-26 with predicted Over chance at line half(proj) (EARLY/LATE pricers)."""
    if stat in _EVAL:
        return _EVAL[stat]
    s = props.project(d, stat).reset_index(drop=True)
    out = []
    for train, test in (((2013, 2018), (2019, 2022)), ((2013, 2022), (2023, 2026))):
        pr = props.Pricer(s, stat, train)
        ev = s[s.season.between(*test) & s.proj.notna() & (s.proj > 0) & (s._n >= 3)].copy()
        L, P = [], []
        for _, r in ev.iterrows():
            if stat == 'anytime_td':
                L.append(np.nan); P.append(pr.p_over(r.position, r.proj)); continue
            l_ = props.half(r.proj)
            L.append(l_); P.append(pr.p_over(r.position, r.proj, l_) if l_ >= 0.5 else np.nan)
        ev['L'] = L; ev['p_over'] = P; ev['period'] = 'early' if test[0] == 2019 else 'late'
        out.append(ev[ev.p_over.notna()])
    e = pd.concat(out, ignore_index=True)
    e['nm'] = e.player_display_name.map(norm)
    if stat == 'anytime_td':
        e['hit_over'] = (e._v >= 1).astype(float); e['hit_under'] = (e._v < 1).astype(float)
    else:
        e['hit_over'] = (e._v > e.L).astype(float); e['hit_under'] = (e._v < e.L).astype(float)
    _EVAL[stat] = e
    return e


def prop_result(x, side):
    res = {}
    for per in ('early', 'late'):
        y = x[x.period == per]
        p = y.p_over if side == 'over' else 1 - y.p_over
        h = y.hit_over if side == 'over' else y.hit_under
        res[per] = dict(n=int(len(y)), hits=int(h.sum()), actual=float(h.mean()) if len(y) else float('nan'),
                        predicted=float(p.mean()) if len(y) else float('nan'))
    e, l = res['early'], res['late']
    ge, gl = e['actual'] - e['predicted'], l['actual'] - l['predicted']
    n = e['n'] + l['n']; k = e['hits'] + l['hits']
    p0 = (e['predicted'] * e['n'] + l['predicted'] * l['n']) / n if n else 0.5
    pv = binom_p_above(k, n, p0) if n else 1.0
    ok = bool(ge >= 0.03 and gl >= 0.03 and e['n'] >= 100 and l['n'] >= 100 and pv < 0.05)
    return dict(early=e, late=l, gap_early=ge, gap_late=gl, p=pv, passes=ok, side=side)


def game_result(x, win, push, ep, lp):
    out = {}
    for nm, (a, b) in (('early', ep), ('late', lp)):
        y = x[x.season.between(a, b) & ~push[x.index]]
        out[nm] = (int(win[y.index].sum()), int(len(y)))
    e, l = out['early'], out['late']
    pe = e[0] / e[1] if e[1] else float('nan'); pl = l[0] / l[1] if l[1] else float('nan')
    p = grade.binom_p_above_half(e[0] + l[0], e[1] + l[1])
    ok = bool(e[1] >= 100 and l[1] >= 100 and pe >= 0.524 and pl >= 0.524 and p < 0.05)
    return dict(early=e, late=l, early_pct=pe, late_pct=pl, p=p, passes=ok)


def temp(t):
    m = re.search(r'temp:\s*(-?\d+)', str(t).lower())
    return int(m.group(1)) if m else np.nan


if __name__ == '__main__':
    g = games(); tg = team_games(g); d = props.weekly(); sn = snaps()
    w = v6.weather(); w['temp_f'] = w.weather.map(temp)
    print('data loaded', flush=True)
    DO = def_out(tg, sn); print('def starters out computed', len(DO), flush=True)
    REC, RB = key_out(tg, d, sn); print('key receivers out', len(REC), 'key RBs out', len(RB), flush=True)
    R, lines = {}, []

    # ---- props
    ctx = tg.set_index(['game_id', 'team'])
    def with_ctx(e):
        return e.join(ctx[['itt', 'fav']], on=['game_id', 'team'])
    P = {s_: with_ctx(evals(d, s_)) for s_ in ('passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'anytime_td')}
    print('projections priced', flush=True)
    py, ry, cy = P['passing_yards'], P['rushing_yards'], P['receiving_yards']
    tests = [
        ('A1 passing yds OVER, team total 26.5+', py[py.itt >= 26.5], 'over'),
        ('A2 passing yds UNDER, team total 19.5-', py[py.itt <= 19.5], 'under'),
        ('A3 rushing yds OVER, team total 26.5+', ry[ry.itt >= 26.5], 'over'),
        ('A4 rushing yds UNDER, team total 19.5-', ry[ry.itt <= 19.5], 'under'),
        ('A5 receiving yds OVER, team total 26.5+', cy[cy.itt >= 26.5], 'over'),
        ('A6 receiving yds UNDER, team total 19.5-', cy[cy.itt <= 19.5], 'under'),
        ('A7 RB rushing yds OVER, team favored 7+', ry[(ry.position == 'RB') & (ry.fav >= 7)], 'over'),
        ('A8 QB passing yds OVER, team 7+ underdog', py[(py.position == 'QB') & (py.fav <= -7)], 'over'),
    ]
    rec_t = {(a, b) for a, b, _ in REC}; rb_t = {(a, b) for a, b, _ in RB}
    rec_nm = {(a, b): {n for a2, b2, n in REC if (a2, b2) == (a, b)} for a, b in rec_t}
    rb_nm = {(a, b): {n for a2, b2, n in RB if (a2, b2) == (a, b)} for a, b in rb_t}
    def mate(e, keys, names, pos):
        k = list(zip(e.game_id, e.team))
        m = np.array([(kk in keys) and (nm not in names.get(kk, ())) for kk, nm in zip(k, e.nm)]) & e.position.isin(pos).values
        return e[m]
    tests += [
        ('B1 receiving yds OVER, key receiver out', mate(cy, rec_t, rec_nm, ['WR', 'TE']), 'over'),
        ('B2 receptions OVER, key receiver out', mate(P['receptions'], rec_t, rec_nm, ['WR', 'TE']), 'over'),
        ('B3 rushing yds OVER, key RB out', mate(ry, rb_t, rb_nm, ['RB']), 'over'),
    ]
    dbo = DO.set_index(['game_id', 'team']).db_out
    opp = tg[['game_id', 'team']].merge(tg[['game_id', 'team']], on='game_id', suffixes=('', '_opp'))
    opp = opp[opp.team != opp.team_opp].set_index(['game_id', 'team']).team_opp
    q = py[py.position == 'QB'].copy()
    q['opp_db_out'] = [dbo.get((gid, opp.get((gid, t))), np.nan) for gid, t in zip(q.game_id, q.team)]
    tests.append(('C3 QB passing yds OVER, 2+ starting DBs out on defense', q[q.opp_db_out >= 2], 'over'))
    wt = w.set_index('game_id')
    py2 = py.join(wt[['temp_f', 'bad']], on='game_id')
    tests.append(('D2 passing yds UNDER, cold 32F or less', py2[py2.temp_f <= 32], 'under'))
    for st, key, side in (('receptions', 'E1 receptions UNDER, bad weather', 'under'), ('anytime_td', 'E2 anytime TD - NO TD, bad weather', 'under')):
        x = P[st].join(wt[['bad']], on='game_id')
        tests.append((key, x[x.bad == True], side))
    lines.append('PROPS - line = v3 projection rounded to x.5; actual vs model chance for that side; needs +3.0 pts both periods')
    for name, x, side in tests:
        r = prop_result(x, side); R[name] = r
        e, l = r['early'], r['late']
        lines.append(f"  {name:52s} 2019-22 n={e['n']:5d} {e['actual']:.1%} vs {e['predicted']:.1%} ({r['gap_early']*100:+.1f}) | "
                     f"2023-26 n={l['n']:5d} {l['actual']:.1%} vs {l['predicted']:.1%} ({r['gap_late']*100:+.1f}) | p={r['p']:.3f} | {'PASS' if r['passes'] else 'FAIL'}")

    # ---- game tests
    gg = g.set_index('game_id')
    dd = DO.pivot_table(index='game_id', columns=DO.groupby('game_id').cumcount(), values='d_out')
    DOt = DO.set_index(['game_id', 'team']).d_out
    G = g.copy()
    G['h_out'] = [DOt.get((i, t), np.nan) for i, t in zip(G.game_id, G.home_team)]
    G['a_out'] = [DOt.get((i, t), np.nan) for i, t in zip(G.game_id, G.away_team)]
    G = G[G.h_out.notna() & G.a_out.notna()].reset_index(drop=True)
    c1 = G[(G.h_out >= 3) | (G.a_out >= 3)]
    win = c1.total > c1.total_line; push = c1.total == c1.total_line
    R['C1 total OVER, a defense with 3+ starters out'] = game_result(c1, win, push, (2012, 2018), (2019, 2026))
    # C2: take the team facing the depleted defense
    hs = (G.a_out >= 3) & (G.h_out <= 1); as_ = (G.h_out >= 3) & (G.a_out <= 1)
    c2 = G[hs | as_].copy()
    marg = np.where(hs[c2.index], c2.result - c2.spread_line, -(c2.result - c2.spread_line))   # home covers if result > spread_line
    c2win = pd.Series(marg > 0, index=c2.index); c2push = pd.Series(marg == 0, index=c2.index)
    R['C2 spread: team facing 3+ defensive starters out'] = game_result(c2, c2win, c2push, (2012, 2018), (2019, 2026))
    gw = g.merge(w[['game_id', 'temp_f']], on='game_id')
    d1 = gw[gw.temp_f <= 32].reset_index(drop=True)
    R['D1 total UNDER, cold 32F or less'] = game_result(d1, d1.total < d1.total_line, d1.total == d1.total_line, (2006, 2016), (2017, 2026))
    lines.append('\nGAMES - graded at -110 (needs 52.4% both periods), pushes out')
    for name in ('C1 total OVER, a defense with 3+ starters out', 'C2 spread: team facing 3+ defensive starters out', 'D1 total UNDER, cold 32F or less'):
        r = R[name]
        lines.append(f"  {name:52s} EARLY {r['early'][0]}/{r['early'][1]} = {r['early_pct']:.1%} | LATE {r['late'][0]}/{r['late'][1]} = {r['late_pct']:.1%} | p={r['p']:.3f} | {'PASS' if r['passes'] else 'FAIL'}")
    txt = '\n'.join(lines); print(txt)
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    open(os.path.join(HERE, 'results', 'v7_test.txt'), 'w').write('v7 overlooked-variables test (v7/PROTOCOL.md)\n' + txt + '\n')
    json.dump(R, open(os.path.join(HERE, 'results', 'v7_test.json'), 'w'), indent=1, default=float)
