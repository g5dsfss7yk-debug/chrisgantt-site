"""v11 ONE combined game model (rules: v11/PROTOCOL.md + amendment 1, committed first).
python v11/model.py test   -> v11/results/v11_test.txt/json
Features = v3 game features + weather severity + backup QB + key receiver/RB out + defensive starters out + props yardage."""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
for p in ('v3', 'v6', 'v7', 'v8'):
    sys.path.insert(0, os.path.join(ROOT, p))
import nfl, grade, props
import backtest_nfl as bt
import test_v7 as v7

CACHE = os.path.join(ROOT, 'data', 'v11'); os.makedirs(CACHE, exist_ok=True)
NEW_S = ['backup_d', 'recout_d', 'rbout_d', 'dout_d', 'yds_d']
NEW_T = ['gustx', 'rainx', 'coldx', 'backup_s', 'recout_s', 'rbout_s', 'dout_s', 'yds_s']
SPREAD_X = nfl.SPREAD_X + NEW_S
TOTAL_X = nfl.TOTAL_X + NEW_T


def _order(season, gtype, week):
    return season * 100 + np.where(gtype == 'REG', 0, 30) + week


def team_yds(d, sn):
    """Per (game_id, team): starting QB's prior passing-yards average + every active RB/QB's prior rushing average."""
    a = 0.5 ** (1 / props.HL)
    P = {}
    for stat in ('passing_yards', 'rushing_yards'):
        s = props.project(d, stat)
        s['nm'] = s.player_display_name.map(v7.norm)
        P[stat] = {}
        for nm, x in s.sort_values('order').groupby('nm'):
            num = den = 0.0
            for vv in x._v.values:
                num, den = num * a + vv, den * a + 1
            P[stat][nm] = (x.order.values, x.p_avg.values, num / den if den else np.nan)

    def prior(stat, nm, o):
        if nm not in P[stat]:
            return 0.0
        ords, pav, post = P[stat][nm]
        i = np.searchsorted(ords, o, side='left')
        v = pav[i] if i < len(ords) else post
        return 0.0 if (v is None or np.isnan(v)) else float(v)

    x = sn[(sn.offense_snaps > 0) & sn.position.isin(['QB', 'RB'])].copy()
    gt = v7.data.nfl_games(refresh_hours=999).set_index('game_id').game_type
    x['order'] = _order(x.season.values, x.game_id.map(gt).fillna('REG').values, x.week.values)
    out = {}
    for (gid, team), y in x.groupby(['game_id', 'team']):
        o = int(y.order.iloc[0])
        qb = y[y.position == 'QB'].sort_values('offense_snaps').tail(1)
        val = prior('passing_yards', qb.nm.iloc[0], o) if len(qb) else 0.0
        val += sum(prior('rushing_yards', nm, o) for nm in y.nm)
        out[(gid, team)] = val
    return out


def build():
    p = os.path.join(CACHE, 'features.pkl')
    if os.path.exists(p):
        return pd.read_pickle(p)
    f = pd.read_pickle(os.path.join(ROOT, 'v3', 'results', 'nfl_backtest.pkl'))
    f = f.sort_values('gameday').reset_index(drop=True)
    # backup QB: earlier starts in the data
    seen, bh, ba = {}, [], []
    for hq, aq in zip(f.h_qb, f.a_qb):
        bh.append(float(seen.get(hq, 0) < 4)); ba.append(float(seen.get(aq, 0) < 4))
        seen[hq] = seen.get(hq, 0) + 1; seen[aq] = seen.get(aq, 0) + 1
    f['backup_h'], f['backup_a'] = bh, ba
    # weather (v9 hourly), outdoor only
    W = pd.read_csv(os.path.join(ROOT, 'data', 'v9', 'game_weather.csv')).set_index('game_id')
    f['gustx'] = f.game_id.map((W.gust - 15).clip(lower=0)).fillna(0.0)
    f['rainx'] = f.game_id.map(W.rain.clip(upper=1.0)).fillna(0.0)
    f['coldx'] = f.game_id.map((40 - W.temp).clip(lower=0)).fillna(0.0)
    # key players / defensive starters out (v7 definitions)
    g = v7.games(); tg = v7.team_games(g); sn = v7.snaps(); d = props.weekly()
    import model as v8model
    ctx = v8model.features()
    rec = pd.Series(1, index=pd.MultiIndex.from_tuples([(a, b) for a, b, _ in ctx['rec']])).groupby(level=[0, 1]).sum()
    rb = pd.Series(1, index=pd.MultiIndex.from_tuples([(a, b) for a, b, _ in ctx['rb']])).groupby(level=[0, 1]).sum()
    DO = v7.def_out(tg, sn).set_index(['game_id', 'team']).d_out
    Y = team_yds(d, sn)
    for side, col in (('h', 'home_team'), ('a', 'away_team')):
        k = list(zip(f.game_id, f[col]))
        f[f'recout_{side}'] = [float(rec.get(x, 0)) for x in k]
        f[f'rbout_{side}'] = [float(rb.get(x, 0)) for x in k]
        f[f'dout_{side}'] = [float(DO.get(x, 0)) for x in k]
        f[f'yds_{side}'] = [Y.get(x, np.nan) for x in k]
    for v in ('backup', 'recout', 'rbout', 'dout', 'yds'):
        f[f'{v}_d'] = f[f'{v}_h'] - f[f'{v}_a']; f[f'{v}_s'] = f[f'{v}_h'] + f[f'{v}_a']
    f.to_pickle(p)
    return f


def walk_forward(f, first, last, fit_from=2013):
    f = f.copy(); f['pm11'], f['pt11'] = np.nan, np.nan
    ok_s, ok_t = f[SPREAD_X].notna().all(1), f[TOTAL_X].notna().all(1)
    for s in range(first, last + 1):
        tr = (f.season >= fit_from) & (f.season < s) & f.result.notna(); te = f.season == s
        b = nfl._ols(f.loc[tr & ok_s, SPREAD_X].values, f.loc[tr & ok_s, 'result'].values)
        f.loc[te & ok_s, 'pm11'] = nfl._pred(b, f.loc[te & ok_s, SPREAD_X].values)
        b = nfl._ols(f.loc[tr & ok_t, TOTAL_X].values, f.loc[tr & ok_t, 'total'].values)
        f.loc[te & ok_t, 'pt11'] = nfl._pred(b, f.loc[te & ok_t, TOTAL_X].values)
    return f


def fit_final(f, upto, fit_from=2013):
    tr = (f.season >= fit_from) & (f.season <= upto) & f.result.notna()
    ok_s, ok_t = f[SPREAD_X].notna().all(1), f[TOTAL_X].notna().all(1)
    bs = nfl._ols(f.loc[tr & ok_s, SPREAD_X].values, f.loc[tr & ok_s, 'result'].values)
    btt = nfl._ols(f.loc[tr & ok_t, TOTAL_X].values, f.loc[tr & ok_t, 'total'].values)
    sd = (f.loc[tr & ok_s, 'result'].values - nfl._pred(bs, f.loc[tr & ok_s, SPREAD_X].values)).std()
    return bs, btt, sd


if __name__ == '__main__':
    f = build(); print('features built', len(f), flush=True)
    f = walk_forward(f, 2014, 2026)
    EARLY, LATE = (2014, 2018), (2019, 2026)
    both = f[f.pm11.notna() & f.pm.notna() & f.pt11.notna() & f.pt.notna()]
    out, lines = {}, [f'v11 vs v3 on the SAME games (both priced): {len(both)} games 2014-26']
    for kind, fn, c11, c3 in (('spread', bt.spread_bets, 'pm11', 'pm'), ('total', bt.total_bets, 'pt11', 'pt')):
        for thr in (0, 1, 2):
            res = {}
            for name, col in (('v11', c11), ('v3', c3)):
                g_ = both.copy(); g_['pm' if kind == 'spread' else 'pt'] = g_[col]
                r = {}
                for per, (a_, b_) in (('early', EARLY), ('late', LATE)):
                    w, p_, pr, _ = fn(g_[(g_.season >= a_) & (g_.season <= b_)], thr)
                    r[per] = grade.record(w, pr, p_)
                r['pass'] = grade.passes(r['early'], r['late'])
                res[name] = r
            key = f'{kind} edge {thr}+'
            out[key] = res
            e11, l11, e3, l3 = res['v11']['early'], res['v11']['late'], res['v3']['early'], res['v3']['late']
            lines.append(f"{key:15s} v11 {grade.fmt(e11):38s} | {grade.fmt(l11):38s} {'TESTED PICK' if res['v11']['pass'] else 'LEAN':11s} || "
                         f"v3 {grade.fmt(e3):38s} | {grade.fmt(l3):38s}")
    rep = {k: out[f'{k} edge 0+']['v11']['early']['pct'] > out[f'{k} edge 0+']['v3']['early']['pct'] and
               out[f'{k} edge 0+']['v11']['late']['pct'] > out[f'{k} edge 0+']['v3']['late']['pct'] for k in ('spread', 'total')}
    lines.append(f"v11 replaces v3 (all-games hit rate higher in BOTH periods): spreads {rep['spread']}, totals {rep['total']}")
    bs, btt, _ = fit_final(f, 2025)
    lines.append('coefficients (fit 2013-25): spread ' + ', '.join(f'{n} {v:+.3f}' for n, v in zip(['const'] + SPREAD_X, bs)))
    lines.append('                           total  ' + ', '.join(f'{n} {v:+.3f}' for n, v in zip(['const'] + TOTAL_X, btt)))
    txt = '\n'.join(lines); print(txt)
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    open(os.path.join(HERE, 'results', 'v11_test.txt'), 'w').write('v11 one combined game model (v11/PROTOCOL.md). EARLY 2014-18 | LATE 2019-26\n' + txt + '\n')
    json.dump(dict(results=out, replaces=rep), open(os.path.join(HERE, 'results', 'v11_test.json'), 'w'), indent=1, default=float)
