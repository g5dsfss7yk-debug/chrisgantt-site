"""v3 college model (built from scratch; see v3/PROTOCOL.md).

Before every slate (season, week): opponent-adjusted team ratings from a time-weighted ridge regression
on (1) per-game offensive PPA (offense rating, defense rating) and (2) point margin. FCS teams included.
Then OLS of home margin / total on the market line + ratings, fit walk-forward on earlier seasons.
CFBD sign: spread is the HOME number (-7 = home favored). Here 'line' = expected home margin = -spread.
"""
import numpy as np
import pandas as pd
import data

LAMBDA = 5.0
PLAYS = 70.0
FIRST = 2012


def load(seasons):
    G, A, L = [], [], []
    for y in seasons:
        g = data.cfb_games(y)
        G.append(g[['id', 'season', 'week', 'seasonType', 'startDate', 'neutralSite', 'homeTeam', 'awayTeam',
                    'homeClassification', 'awayClassification', 'homePoints', 'awayPoints', 'completed']])
        A.append(data.cfb_adv(y))
        if y >= 2013:
            L.append(data.cfb_lines(y))
    g = pd.concat(G, ignore_index=True)
    g = g[(g.homeClassification == 'fbs') | (g.awayClassification == 'fbs')].reset_index(drop=True)
    g['stype'] = np.where(g.seasonType == 'regular', 0, 1)
    g['slate_key'] = g.season * 100 + g.stype * 50 + g.week
    keys = np.sort(g.slate_key.unique())
    g['seq'] = np.searchsorted(keys, g.slate_key)
    g['margin'] = g.homePoints - g.awayPoints
    g['tot'] = g.homePoints + g.awayPoints
    a = pd.concat(A, ignore_index=True)
    lines = pd.concat(L, ignore_index=True).dropna(subset=['spread'])
    lines = lines[lines.spread.abs() < 80]
    med = lines.groupby('id').agg(med_spread=('spread', 'median'), med_total=('total', 'median'))
    dk = lines[lines.provider == 'DraftKings'].groupby('id').agg(dk_spread=('spread', 'first'), dk_total=('total', 'first'),
                                                                   dk_home_ml=('home_ml', 'first'), dk_away_ml=('away_ml', 'first'))
    oth = lines[lines.provider != 'DraftKings'].groupby('id').agg(oth_spread=('spread', 'median'))
    g = g.merge(med, left_on='id', right_index=True, how='left').merge(dk, left_on='id', right_index=True, how='left') \
         .merge(oth, left_on='id', right_index=True, how='left')
    g['spread_used'] = g.dk_spread.fillna(g.med_spread)
    g['total_used'] = g.dk_total.fillna(g.med_total)
    g['line'] = -g.spread_used
    return g, a


def _ridge(rows_team, rows_opp, signs_opp, loc, y, w, teams, two_params):
    """Weighted ridge. two_params: offense O[team] and defense D[opp] (y = mu + O_t - D_o + h*loc);
    else one rating R (y = h*loc + R_t - R_o)."""
    nT = len(teams)
    k = 2 * nT + 2 if two_params else nT + 1
    n = len(y)
    X = np.zeros((n, k))
    r = np.arange(n)
    if two_params:
        X[r, rows_team] = 1.0
        X[r, nT + rows_opp] = -1.0
        X[:, 2 * nT] = 1.0
        X[:, 2 * nT + 1] = loc
        pen = np.r_[np.full(2 * nT, LAMBDA), 1e-6, 1e-6]
    else:
        X[r, rows_team] = 1.0
        X[r, rows_opp] = -1.0
        X[:, nT] = loc
        pen = np.r_[np.full(nT, LAMBDA), 1e-6]
    Xw = X * w[:, None]
    beta = np.linalg.solve(X.T @ Xw + np.diag(pen), Xw.T @ y)
    return beta


def slate_ratings(g, a, seq_now, season_now, H, Gap, window=60):
    past = g[(g.seq < seq_now) & (g.seq >= seq_now - window) & g.completed.fillna(False) & g.margin.notna()]
    if len(past) < 50:
        return None
    age = (seq_now - past.seq.values) + Gap * (season_now - past.season.values)
    w = 0.5 ** (age / H)
    teams = pd.Index(pd.unique(np.r_[past.homeTeam.values, past.awayTeam.values]))
    hi, ai = teams.get_indexer(past.homeTeam), teams.get_indexer(past.awayTeam)
    loc = np.where(past.neutralSite.fillna(False).values, 0.0, 1.0)
    br = _ridge(hi, ai, None, loc, past.margin.values.astype(float), w, teams, False)
    R = pd.Series(br[:len(teams)], index=teams)
    # PPA: one row per team-offense game
    ap = a.drop(columns=['season', 'week']).merge(past[['id', 'seq', 'season', 'homeTeam', 'neutralSite']], on='id')
    ap = ap[ap.o_ppa.notna() & ap.team.isin(teams) & ap.opp.isin(teams)]
    age2 = (seq_now - ap.seq.values) + Gap * (season_now - ap.season.values)
    w2 = 0.5 ** (age2 / H)
    loc2 = np.where(ap.neutralSite.fillna(False).values, 0.0, np.where(ap.team.values == ap.homeTeam.values, 1.0, -1.0))
    bp = _ridge(teams.get_indexer(ap.team), teams.get_indexer(ap.opp), None, loc2, ap.o_ppa.values.astype(float),
                w2, teams, True)
    O = pd.Series(bp[:len(teams)], index=teams)
    D = pd.Series(bp[len(teams):2 * len(teams)], index=teams)
    mu = bp[2 * len(teams)]
    pw = pd.DataFrame({'t': ap.team.values, 'w': w2, 'p': ap.o_plays.values * w2})
    pw = pw.groupby('t').sum()
    pace = (pw.p / pw.w)
    return R, O, D, mu, pace


def features(g, a, H, Gap, seasons):
    out = []
    for seq_now in sorted(g[g.season.isin(seasons)].seq.unique()):
        s = g[g.seq == seq_now]
        season = int(s.season.iloc[0])
        r = slate_ratings(g, a, seq_now, season, H, Gap)
        if r is None:
            continue
        R, O, D, mu, pace = r
        s = s.copy()
        gr = lambda S, t, d=0.0: S.reindex(t).fillna(d).values
        s['pts_diff'] = gr(R, s.homeTeam) - gr(R, s.awayTeam)
        s['ppa_diff'] = ((gr(O, s.homeTeam) - gr(D, s.awayTeam)) - (gr(O, s.awayTeam) - gr(D, s.homeTeam))) * PLAYS
        s['ppa_sum'] = ((gr(O, s.homeTeam) - gr(D, s.awayTeam)) + (gr(O, s.awayTeam) - gr(D, s.homeTeam)) + 2 * mu) * PLAYS
        pm = float(pace.median())
        s['pace2'] = gr(pace, s.homeTeam, pm) + gr(pace, s.awayTeam, pm)
        s['home'] = np.where(s.neutralSite.fillna(False), 0.0, 1.0)
        out.append(s)
    return pd.concat(out, ignore_index=True)


SPREAD_X = ['line', 'ppa_diff', 'pts_diff', 'home']
TOTAL_X = ['total_used', 'ppa_sum', 'pace2']


def _ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    return np.linalg.lstsq(X1, y, rcond=None)[0]


def _pred(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


def walk_forward(f, first_test, last_test, fit_from=2013):
    f = f.copy()
    f['pm'], f['pt'], f['sd'] = np.nan, np.nan, np.nan
    ok_s = f[SPREAD_X].notna().all(1) & f.margin.notna()
    ok_t = f[TOTAL_X].notna().all(1) & f.tot.notna()
    for s in range(first_test, last_test + 1):
        tr = (f.season >= fit_from) & (f.season < s)
        te = (f.season == s)
        b = _ols(f.loc[tr & ok_s, SPREAD_X].values, f.loc[tr & ok_s, 'margin'].values)
        f.loc[te & f[SPREAD_X].notna().all(1), 'pm'] = _pred(b, f.loc[te & f[SPREAD_X].notna().all(1), SPREAD_X].values)
        f.loc[te, 'sd'] = (f.loc[tr & ok_s, 'margin'].values - _pred(b, f.loc[tr & ok_s, SPREAD_X].values)).std()
        bt = _ols(f.loc[tr & ok_t, TOTAL_X].values, f.loc[tr & ok_t, 'tot'].values)
        m = te & f[TOTAL_X].notna().all(1)
        f.loc[m, 'pt'] = _pred(bt, f.loc[m, TOTAL_X].values)
    return f


def fit_final(f, upto_season, fit_from=2013):
    tr = (f.season >= fit_from) & (f.season <= upto_season)
    ok_s = tr & f[SPREAD_X].notna().all(1) & f.margin.notna()
    ok_t = tr & f[TOTAL_X].notna().all(1) & f.tot.notna()
    bs = _ols(f.loc[ok_s, SPREAD_X].values, f.loc[ok_s, 'margin'].values)
    bt = _ols(f.loc[ok_t, TOTAL_X].values, f.loc[ok_t, 'tot'].values)
    sd = (f.loc[ok_s, 'margin'].values - _pred(bs, f.loc[ok_s, SPREAD_X].values)).std()
    return bs, bt, sd
