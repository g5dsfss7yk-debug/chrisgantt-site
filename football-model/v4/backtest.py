"""v4 ideas A-D (v4/PROTOCOL.md), run once. Uses the v3 walk-forward feature tables (v3/results/*_backtest.pkl).
  python football-model/v4/backtest.py"""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'v3'))
import grade, data, nfl as v3nfl, cfb as v3cfb  # noqa

V3R = os.path.join(HERE, '..', 'v3', 'results')
RES = os.path.join(HERE, 'results'); os.makedirs(RES, exist_ok=True)
NFL_E, NFL_L = (2006, 2016), (2017, 2026)
CFB_E, CFB_L = (2014, 2022), (2023, 2026)


def ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X]); return np.linalg.lstsq(X1, y, rcond=None)[0]


def pred(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


def per(d, p):
    return d[(d.season >= p[0]) & (d.season <= p[1])]


def rec_side(margin, line_home, home_pick):
    """margin = home - away; line_home = expected home margin (market). home_pick bool array."""
    ats = margin - line_home
    win = np.where(home_pick, ats > 0, ats < 0)
    return grade.record(win, None, ats == 0)


def rec_total(tot, line, over_pick):
    win = np.where(over_pick, tot > line, tot < line)
    return grade.record(win, None, tot == line)


def walk(f, seasons, fit_from, xcols, ycol, okmask, extra=None):
    """Walk-forward OLS; returns predictions and (for idea A) per-row P(over) using in-sample training residuals."""
    p = pd.Series(np.nan, index=f.index)
    pover = pd.Series(np.nan, index=f.index)
    for s in seasons:
        tr = (f.season >= fit_from) & (f.season < s) & okmask
        te = (f.season == s) & f[xcols].notna().all(1)
        if tr.sum() < 100:
            continue
        b = ols(f.loc[tr, xcols].values, f.loc[tr, ycol].values)
        p[te] = pred(b, f.loc[te, xcols].values)
        if extra is not None:   # idea A: residual distribution of the training fit
            res = np.sort(f.loc[tr, ycol].values - pred(b, f.loc[tr, xcols].values))
            gap = f.loc[te, extra].values - p[te].values          # line - predicted
            pover[te] = 1 - np.searchsorted(res, gap, side='right') / len(res)
    return p, pover


def ml_mapping_bets(df, season_list, ml_h, ml_a, line_col):
    """Idea C. line_col = expected home margin. Cubic of line on logit(no-vig home chance), fit on earlier seasons."""
    d = df.dropna(subset=[ml_h, ml_a, line_col]).copy()
    ih, ia = 1 / grade.dec(d[ml_h]), 1 / grade.dec(d[ml_a])
    ph = np.clip(ih / (ih + ia), 0.005, 0.995)
    d['lg'] = np.log(ph / (1 - ph))
    d['imp'] = np.nan
    for s in season_list:
        tr, te = d.season < s, d.season == s
        if tr.sum() < 200 or te.sum() == 0:
            continue
        c = np.polyfit(d.loc[tr, 'lg'], d.loc[tr, line_col], 3)
        d.loc[te, 'imp'] = np.polyval(c, d.loc[te, 'lg'])
    d = d[d.imp.notna()]
    gap = d.imp - d[line_col]
    return d[gap.abs() >= 1], (gap[gap.abs() >= 1] > 0).values   # home pick when ML thinks home is better


def nfl_part(out, lines):
    f = pd.read_pickle(os.path.join(V3R, 'nfl_backtest.pkl'))
    f = f[f.season >= 2003].copy()
    seasons = range(NFL_E[0], NFL_L[1] + 1)
    ok_t = f[v3nfl.TOTAL_X].notna().all(1) & f.total.notna()
    _, f['pover'] = walk(f, seasons, 2003, v3nfl.TOTAL_X, 'total', ok_t, extra='total_line')
    BX = ['net', 'qbd', 'home']
    ok_b = f[BX].notna().all(1) & f.result.notna()
    f['pb'], _ = walk(f, seasons, 2003, BX, 'result', ok_b)
    F = f[f.result.notna()]

    def A(d, thr):
        d = d[d.pover.notna()]
        pk = d.pover > 0.5
        conf = np.where(pk, d.pover, 1 - d.pover)
        d, pk = d[conf >= thr], pk[conf >= thr]
        return rec_total(d.total.values, d.total_line.values, pk.values)

    def B(d, thr):
        d = d[d.pb.notna()]
        e = d.pb - d.spread_line
        d, e = d[e.abs() >= thr], e[e.abs() >= thr]
        return rec_side(d.result.values, d.spread_line.values, (e > 0).values)

    def C(d):
        g, hp = ml_mapping_bets(d, sorted(F.season.unique()), 'home_moneyline', 'away_moneyline', 'spread_line')
        return rec_side(g.result.values, g.spread_line.values, hp)

    def D(d):
        d = d[d.pb.notna() & d.pm.notna()]
        e3, eb = d.pm - d.spread_line, d.pb - d.spread_line
        m = (np.sign(e3) == np.sign(eb)) & (eb.abs() >= 3)
        return rec_side(d.result[m].values, d.spread_line[m].values, (eb[m] > 0).values)

    # C needs the mapping fit across all seasons in order, so compute once and split
    gC, hpC = ml_mapping_bets(F, sorted(F.season.unique()), 'home_moneyline', 'away_moneyline', 'spread_line')
    gC = gC.assign(hp=hpC)
    tests = {
        'NFL A total by chance, all games': lambda d: A(d, 0.5),
        'NFL A total by chance, P>=0.55': lambda d: A(d, 0.55),
        'NFL B ratings-only spread, all': lambda d: B(d, 0),
        'NFL B ratings-only spread, edge 3+': lambda d: B(d, 3),
        'NFL C moneyline vs spread gap 1+': lambda d: (lambda g: rec_side(g.result.values, g.spread_line.values, g.hp.values))(gC[gC.game_id.isin(d.game_id)]),
        'NFL D v3 + ratings agree, edge 3+': D,
    }
    for name, fn in tests.items():
        e, l = fn(per(F, NFL_E)), fn(per(F, NFL_L))
        ok = grade.passes(e, l)
        out[name] = {'early': e, 'late': l, 'pass': ok}
        lines.append(f"{name:36s} EARLY {grade.fmt(e):44s} LATE {grade.fmt(l):44s} -> {'PASS' if ok else 'fail'}")
    L = per(F, NFL_L).dropna(subset=['pm', 'pb'])
    mse = lambda x: float(np.mean((L.result - x) ** 2))
    lines.append(f"  NFL LATE squared error: line {mse(L.spread_line):.1f}, v3 model {mse(L.pm):.1f}, ratings-only {mse(L.pb):.1f} (lower = more predictive)")
    ovs = per(F, NFL_L).pover.dropna()
    lines.append(f"  NFL idea A picks Over in {(ovs > 0.5).mean():.0%} of LATE games (v3 picked Over in ~70-79%)")


def cfb_part(out, lines):
    f = pd.read_pickle(os.path.join(V3R, 'cfb_backtest.pkl')).copy()
    seasons = range(CFB_E[0], CFB_L[1] + 1)
    # graded lines: EARLY median of books, LATE DraftKings
    late = f.season >= CFB_L[0]
    f['g_line'] = np.where(late, -f.dk_spread, -f.med_spread)
    f['g_total'] = np.where(late, f.dk_total, f.med_total)
    ok_t = f[v3cfb.TOTAL_X].notna().all(1) & f.tot.notna()
    # P(over) at the graded total: predict with the graded total as the line input
    _, pov = walk(f, seasons, 2013, v3cfb.TOTAL_X, 'tot', ok_t, extra='g_total')
    f['pover'] = pov
    BX = ['ppa_diff', 'pts_diff', 'home']
    ok_b = f[BX].notna().all(1) & f.margin.notna()
    f['pb'], _ = walk(f, seasons, 2013, BX, 'margin', ok_b)
    F = f[f.margin.notna()]
    F = F[~((F.season >= CFB_L[0]) & F.dk_spread.isna())]   # LATE bets only where DK has a line

    def A(d, thr):
        d = d[d.pover.notna() & d.g_total.notna()]
        pk = d.pover > 0.5
        conf = np.where(pk, d.pover, 1 - d.pover)
        d, pk = d[conf >= thr], pk[conf >= thr]
        return rec_total(d.tot.values, d.g_total.values, pk.values)

    def B(d, thr):
        d = d[d.pb.notna() & d.g_line.notna()]
        e = d.pb - d.g_line
        d, e = d[e.abs() >= thr], e[e.abs() >= thr]
        return rec_side(d.margin.values, d.g_line.values, (e > 0).values)

    def D(d):
        d = d[d.pb.notna() & d.pm.notna() & d.g_line.notna()]
        e3, eb = d.pm - d.g_line, d.pb - d.g_line
        m = (np.sign(e3) == np.sign(eb)) & (eb.abs() >= 6)
        return rec_side(d.margin[m].values, d.g_line[m].values, (eb[m] > 0).values)

    # C: same-book spread + moneyline. 2021-22 Bovada, 2023+ DraftKings
    rows = []
    for y in range(2021, 2027):
        Lb = data.cfb_lines(y)
        bk = 'Bovada' if y <= 2022 else 'DraftKings'
        x = Lb[(Lb.provider == bk)].dropna(subset=['spread', 'home_ml', 'away_ml'])
        x = x[x.home_score.notna()]
        rows.append(x.assign(line=-x.spread, margin=x.home_score - x.away_score))
    M = pd.concat(rows, ignore_index=True)
    gC, hpC = ml_mapping_bets(M, range(2021, 2027), 'home_ml', 'away_ml', 'line')
    gC = gC.assign(hp=hpC)
    cE = per(gC, (2021, 2022)); cL = per(gC, CFB_L)
    tests = {
        'CFB A total by chance, all games': lambda d: A(d, 0.5),
        'CFB A total by chance, P>=0.55': lambda d: A(d, 0.55),
        'CFB B ratings-only spread, all': lambda d: B(d, 0),
        'CFB B ratings-only spread, edge 6+': lambda d: B(d, 6),
        'CFB D v3 + ratings agree, edge 6+': D,
    }
    for name, fn in tests.items():
        e, l = fn(per(F, CFB_E)), fn(per(F, CFB_L))
        ok = grade.passes(e, l)
        out[name] = {'early': e, 'late': l, 'pass': ok}
        lines.append(f"{name:36s} EARLY {grade.fmt(e):44s} LATE {grade.fmt(l):44s} -> {'PASS' if ok else 'fail'}")
    e = rec_side(cE.margin.values, cE.line.values, cE.hp.values)
    l = rec_side(cL.margin.values, cL.line.values, cL.hp.values)
    ok = grade.passes(e, l)
    out['CFB C moneyline vs spread gap 1+'] = {'early': e, 'late': l, 'pass': ok}
    lines.append(f"{'CFB C moneyline vs spread gap 1+':36s} EARLY {grade.fmt(e):44s} LATE {grade.fmt(l):44s} -> {'PASS' if ok else 'fail'}"
                 "  (EARLY = 2022 only, Bovada; LATE = DraftKings)")
    L = per(F, CFB_L).dropna(subset=['pm', 'pb', 'g_line'])
    mse = lambda x: float(np.mean((L.margin - x) ** 2))
    lines.append(f"  CFB LATE squared error: DK line {mse(L.g_line):.1f}, v3 model {mse(L.pm):.1f}, ratings-only {mse(L.pb):.1f}")
    ovs = per(F, CFB_L).pover.dropna()
    lines.append(f"  CFB idea A picks Over in {(ovs > 0.5).mean():.0%} of LATE games (v3: ~95%)")


if __name__ == '__main__':
    out, lines = {}, []
    nfl_part(out, lines)
    cfb_part(out, lines)
    txt = '\n'.join(lines)
    print(txt)
    json.dump(out, open(os.path.join(RES, 'v4_results.json'), 'w'), indent=1, default=float)
    open(os.path.join(RES, 'v4_results.txt'), 'w').write('v4 ideas (PROTOCOL.md). LATE periods re-used from v3.\n' + txt + '\n')
