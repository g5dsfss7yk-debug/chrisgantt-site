"""v3 NFL game model (built from scratch; see v3/PROTOCOL.md).

Team ratings = exponentially weighted EPA/play (offense, defense allowed) on competitive plays
(win prob 10-90%), plus a starting-QB adjustment. OLS on the closing line + ratings, fit walk-forward.
nflverse sign: spread_line > 0 = home favored; result = home - away.
"""
import numpy as np
import pandas as pd
import data

FIRST_PBP = 2002
QB_PRIOR_N, QB_PRIOR_V, QB_DB = 200.0, -0.10, 35.0


# ------------------------------------------------------------------ per team-game stats from play-by-play
def team_games(seasons):
    pb = data.nfl_pbp(seasons)
    pr = pb[((pb['pass'] == 1) | (pb['rush'] == 1)) & (pb.two_point_attempt != 1) & pb.epa.notna() & pb.posteam.notna()]
    comp = pr[(pr.wp >= 0.10) & (pr.wp <= 0.90)]
    off = comp.groupby(['game_id', 'posteam']).agg(o_epa=('epa', 'sum'), o_n=('epa', 'size'))
    dfn = comp.groupby(['game_id', 'defteam']).agg(d_epa=('epa', 'sum'), d_n=('epa', 'size'))
    dfn.index.names = ['game_id', 'posteam']
    plays = pr.groupby(['game_id', 'posteam']).size().rename('plays')
    db = pb[(pb.qb_dropback == 1) & pb.epa.notna() & pb.passer_player_id.notna()]
    qb = db.groupby(['game_id', 'posteam', 'passer_player_id']).agg(q_epa=('epa', 'sum'), q_n=('epa', 'size'),
                                                                      name=('passer_player_name', 'first')).reset_index()
    starter = qb.sort_values('q_n').drop_duplicates(['game_id', 'posteam'], keep='last').set_index(['game_id', 'posteam'])
    tg = off.join(dfn, how='outer').join(plays, how='outer')
    tg['qb'] = starter.passer_player_id
    tg['qb_name'] = starter.name
    tg['team_db'] = db.groupby(['game_id', 'posteam']).size()
    tg = tg.reset_index().rename(columns={'posteam': 'team'})
    return tg, qb


def _ew_matrix(season, H, G):
    n = len(season)
    i = np.arange(n + 1)[:, None]          # row n = "next game" (live use)
    j = np.arange(n)[None, :]
    s_i = np.append(season, season[-1] if n else 0)[:, None]
    age = (i - j) + G * (s_i - season[None, :])
    W = np.where(j < i, 0.5 ** (age / H), 0.0)
    return W


def ratings(games, tg, qbg, H, G, next_season=None):
    """For every team-game (and each team's next game) the ratings ENTERING it.
    games: nflverse schedule rows (completed + upcoming). Returns DataFrame keyed by (game_id, team)."""
    sched = []
    for side, opp in (('home', 'away'), ('away', 'home')):
        s = games[['game_id', 'season', 'gameday', f'{side}_team']].rename(columns={f'{side}_team': 'team'})
        sched.append(s)
    sched = pd.concat(sched).merge(tg, on=['game_id', 'team'], how='left').sort_values(['team', 'gameday', 'game_id'])
    # games not played yet: starter = the schedule's listed QB (live cards override it from ESPN first)
    listed = pd.concat([games[['game_id', f'{s}_team', f'{s}_qb_id']].set_axis(['game_id', 'team', 'listed_qb'], axis=1)
                        for s in ('home', 'away')])
    sched = sched.merge(listed, on=['game_id', 'team'], how='left')
    sched['qb'] = sched.qb.where(sched.o_n.notna(), sched.listed_qb)

    # QB career cumulative values (entering each date)
    qbg = qbg.merge(games[['game_id', 'gameday']], on='game_id').sort_values(['passer_player_id', 'gameday'])
    qcum = {}
    for q, d in qbg.groupby('passer_player_id'):
        qcum[q] = (d.gameday.values, np.cumsum(d.q_epa.values), np.cumsum(d.q_n.values))

    def qval(q, day):
        if not isinstance(q, str) or q not in qcum:
            return QB_PRIOR_V
        dates, ce, cn = qcum[q]
        k = np.searchsorted(dates, day, side='left')  # games strictly before day
        e, n = (ce[k - 1], cn[k - 1]) if k > 0 else (0.0, 0.0)
        return (e + QB_PRIOR_N * QB_PRIOR_V) / (n + QB_PRIOR_N)

    out = []
    for team, d in sched.groupby('team'):
        d = d.reset_index(drop=True)
        played = d.o_n.notna().values
        p = d[played].reset_index(drop=True)
        W = _ew_matrix(p.season.values, H, G)  # (np+1, np)
        idx_in_played = np.cumsum(played) - played  # number of played games before each row
        Wr = W[idx_in_played]                     # weights for each schedule row over played games before it
        def wavg(num, den):
            a, b = Wr @ np.nan_to_num(p[num].values), Wr @ np.nan_to_num(p[den].values)
            return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)
        r = pd.DataFrame({'game_id': d.game_id, 'team': team})
        r['off'] = wavg('o_epa', 'o_n')
        r['def'] = wavg('d_epa', 'd_n')
        wsum = Wr.sum(1)
        r['pace'] = np.where(wsum > 0, (Wr @ np.nan_to_num(p.plays.values)) / np.where(wsum > 0, wsum, 1), np.nan)
        r['n_hist'] = idx_in_played
        # QB adjustment: this game's starter vs the QBs in the rating window (valued as of this game)
        qadj = np.full(len(d), np.nan)
        qcodes, quniq = pd.factorize(pd.Series(p.qb.values).fillna('?'))
        onehot = np.zeros((len(p), len(quniq)))
        onehot[np.arange(len(p)), qcodes] = np.nan_to_num(p.team_db.values)
        QW = Wr @ onehot                            # dropback-weighted weight of each QB in the window
        for k in range(len(d)):
            tot = QW[k].sum()
            if idx_in_played[k] == 0 or tot <= 0:
                continue
            day = d.gameday.iloc[k]
            nz = np.nonzero(QW[k] > 1e-9 * tot)[0]
            vals = np.array([qval(quniq[c], day) for c in nz])
            window = (QW[k, nz] * vals).sum() / QW[k, nz].sum()
            qadj[k] = (qval(d.qb.iloc[k], day) - window) * QB_DB
        r['qb'] = d.qb.values
        r['qb_adj'] = qadj
        out.append(r)
    return pd.concat(out, ignore_index=True)


def features(games, rt):
    h = rt.add_prefix('h_').rename(columns={'h_game_id': 'game_id', 'h_team': 'home_team'})
    a = rt.add_prefix('a_').rename(columns={'a_game_id': 'game_id', 'a_team': 'away_team'})
    f = games.merge(h, on=['game_id', 'home_team']).merge(a, on=['game_id', 'away_team'])
    f['home'] = (f.location != 'Neutral').astype(float)
    f['net'] = (f.h_off - f.h_def) - (f.a_off - f.a_def)
    f['qbd'] = f.h_qb_adj.fillna(0) - f.a_qb_adj.fillna(0)
    f['exp_epa'] = (f.h_off + f.a_def) + (f.a_off + f.h_def)
    f['pace2'] = f.h_pace + f.a_pace
    f['qbs'] = f.h_qb_adj.fillna(0) + f.a_qb_adj.fillna(0)
    f['dome'] = f.roof.isin(['dome', 'closed']).astype(float)
    return f


SPREAD_X = ['spread_line', 'net', 'qbd', 'home']
TOTAL_X = ['total_line', 'exp_epa', 'pace2', 'qbs', 'dome']


def _ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    b, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return b


def _pred(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


def walk_forward(f, first_test, last_test, fit_from=2003):
    """Predict each season from an OLS fit on all earlier seasons (>= fit_from)."""
    f = f.copy()
    f['pm'], f['pt'], f['sd'] = np.nan, np.nan, np.nan
    ok_s = f[SPREAD_X].notna().all(1)
    ok_t = f[TOTAL_X].notna().all(1)
    for s in range(first_test, last_test + 1):
        tr = (f.season >= fit_from) & (f.season < s) & f.result.notna()
        te = f.season == s
        b = _ols(f.loc[tr & ok_s, SPREAD_X].values, f.loc[tr & ok_s, 'result'].values)
        f.loc[te & ok_s, 'pm'] = _pred(b, f.loc[te & ok_s, SPREAD_X].values)
        res = f.loc[tr & ok_s, 'result'].values - _pred(b, f.loc[tr & ok_s, SPREAD_X].values)
        f.loc[te, 'sd'] = res.std()
        bt = _ols(f.loc[tr & ok_t, TOTAL_X].values, f.loc[tr & ok_t, 'total'].values)
        f.loc[te & ok_t, 'pt'] = _pred(bt, f.loc[te & ok_t, TOTAL_X].values)
    return f


def build(H, G, seasons=None):
    g = data.nfl_games()
    last = int(g.season.max())
    seasons = seasons or list(range(FIRST_PBP, last + 1))
    g = g[g.season.isin(seasons)].copy()
    tg, qbg = team_games(seasons)
    rt = ratings(g, tg, qbg, H, G)
    return features(g, rt), tg, qbg


def fit_final(f, upto_season, fit_from=2003):
    """Coefficients from every completed game through upto_season (for live cards)."""
    tr = (f.season >= fit_from) & (f.season <= upto_season) & f.result.notna()
    ok_s, ok_t = f[SPREAD_X].notna().all(1), f[TOTAL_X].notna().all(1)
    bs = _ols(f.loc[tr & ok_s, SPREAD_X].values, f.loc[tr & ok_s, 'result'].values)
    bt = _ols(f.loc[tr & ok_t, TOTAL_X].values, f.loc[tr & ok_t, 'total'].values)
    sd = (f.loc[tr & ok_s, 'result'].values - _pred(bs, f.loc[tr & ok_s, SPREAD_X].values)).std()
    return bs, bt, sd
