"""core NFL game model (core/PROTOCOL.md amendments 6-7). Standalone (uses only core/).
python core/nfl.py test    -> walk-forward test + carry-over rules -> core/results/nfl_test.txt/json"""
import os, sys, json, math
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data
from cfb import ratings_for_slate, pval, ml_profit, STATS, H_GRID

FIRST_FIT, EARLY, LATE = 2009, (2011, 2017), (2018, 2026)
LINE_FREE = False   # amendment 12
TOTAL_MODE = 'ols'  # amendment 14: 'ols' | 'median' | 'offset'
CACHE = os.path.join(data.DATA, 'nfl')
EXTRA = ['qb_value', 'backup_qb', 'qb_change', 'off_out', 'def_out', 'off_q', 'def_q', 'rest']
GAME = ['wind_x', 'cold_x', 'wx_missing', 'dome', 'div']        # game-level: total model (div also in margin)
OFFENSE_POS = {'QB', 'RB', 'FB', 'WR', 'TE', 'T', 'G', 'C', 'LT', 'LG', 'RG', 'RT', 'OL'}
SPECIAL_POS = {'K', 'P', 'LS', 'H', 'KR', 'PR', 'PK'}


def team_games(seasons):
    p = data.nfl_pbp(seasons)
    scr = ((p['pass'] == 1) | (p.rush == 1)) & (p.two_point_attempt != 1) & p.posteam.notna() & p.epa.notna()
    p = p[scr & p.wp.between(0.05, 0.95)].copy()
    p['db'] = (p.qb_dropback == 1).astype(float); p['ru'] = ((p.rush == 1) & (p.qb_dropback != 1)).astype(float)
    p['pe'] = p.epa.where(p.db == 1); p['re'] = p.epa.where(p.ru == 1)
    p['to'] = p.interception.fillna(0) + p.fumble_lost.fillna(0)
    p['rtd'] = ((p.return_touchdown == 1) & (p.td_team == p.defteam)).astype(float)     # amendment 7c
    p['ex'] = (p.yards_gained >= 20).astype(float); p['sk'] = p.sack.fillna(0)
    g = p.groupby(['game_id', 'posteam']).agg(
        season=('season', 'first'), week=('week', 'first'), defteam=('defteam', 'first'), home=('home_team', 'first'),
        pass_epa=('pe', 'mean'), rush_epa=('re', 'mean'), success=('success', 'mean'), turnovers=('to', 'sum'),
        sacks=('sk', 'sum'), dropbacks=('db', 'sum'), explosive=('ex', 'mean'), return_td=('rtd', 'sum'), plays=('epa', 'size'))
    g['sack_rate'] = g.sacks / g.dropbacks.where(g.dropbacks > 0)
    g = g.reset_index().rename(columns={'posteam': 'team'})
    s = data.nfl_schedules()[['game_id', 'location']]
    g = g.merge(s, on='game_id', how='left')
    g['loc'] = np.where(g.location == 'Neutral', 0, np.where(g.team == g.home, 1, -1))
    return g


def schedule():
    g = data.nfl_schedules()
    g = g[g.season.between(2006, 2026)].copy()
    g['neutral'] = (g.location == 'Neutral').astype(float)
    g['spread_home'] = -g.spread_line                      # home number like DK (-7 = home favored)
    out = g.roof.isin(['outdoors', 'open'])
    g['wind_x'] = np.where(out, (g.wind - 10).clip(lower=0), 0).astype(float)
    g['cold_x'] = np.where(out, (40 - g.temp).clip(lower=0), 0).astype(float)
    g['wx_missing'] = (out & g.wind.isna()).astype(float)                                # amendment 7b
    g[['wind_x', 'cold_x']] = g[['wind_x', 'cold_x']].fillna(0.0)
    g['dome'] = (~out).astype(float)
    g['div'] = g.div_game.fillna(0).astype(float)
    g['rest_h'] = g.home_rest.clip(upper=14).fillna(14); g['rest_a'] = g.away_rest.clip(upper=14).fillna(14)
    return g


def build(H, seasons=range(2006, 2027)):
    p = os.path.join(CACHE, f'features_H{H}.pkl')
    if os.path.exists(p):
        return pd.read_pickle(p)
    tg = team_games(seasons)
    sl = tg.groupby(['season', 'week']).size().reset_index()[['season', 'week']].sort_values(['season', 'week']).reset_index(drop=True)
    sl['slate_i'] = range(len(sl))
    tg = tg.merge(sl, on=['season', 'week'])
    G = schedule().merge(sl, on=['season', 'week'], how='inner')
    rows = []
    for i, r in sl.iterrows():
        if r.season < 2007:
            continue
        hist = tg[(tg.slate_i < i) & (tg.season >= r.season - 1)]
        R = ratings_for_slate(hist, H, i)
        for _, gm in G[G.slate_i == i].iterrows():
            row = dict(game_id=gm.game_id); loc = 0 if gm.neutral else 1
            for s in STATS:
                mu, off, dfn, home = R[s]
                he = mu + off.get(gm.home_team, 0.0) + dfn.get(gm.away_team, 0.0) + home * loc
                ae = mu + off.get(gm.away_team, 0.0) + dfn.get(gm.home_team, 0.0) - home * loc
                row[f'm_{s}'] = he - ae; row[f't_{s}'] = he + ae
            rows.append(row)
    f = G.merge(pd.DataFrame(rows), on='game_id')
    f = f.merge(extras(), on='game_id', how='left')
    os.makedirs(CACHE, exist_ok=True); f.to_pickle(p)
    return f


# ---------------------------------------------------------------- QB + injuries/starters + rest
def _starters():
    """Rank-1 offense/defense players per (season, team, week) from the team's PREVIOUS available depth chart."""
    out = []
    for y in range(2009, 2027):
        d = data.nfl_depth(y)
        if 'week' in d:
            d = d[(d.depth_team.astype(str) == '1') & d.formation.isin(['Offense', 'Defense'])]
            d = d.assign(team=d.club_code, side=np.where(d.formation == 'Offense', 'O', 'D'), pos=d.position)
            out.append(d[['season', 'team', 'week', 'gsis_id', 'side', 'pos']].dropna(subset=['gsis_id']).assign(dt=pd.NaT))
        else:
            d = d[(d.pos_rank == 1) & ~d.pos_abb.isin(SPECIAL_POS) & ~d.pos_grp.eq('Special Teams')]
            d = d.assign(season=y, side=np.where(d.pos_abb.isin(OFFENSE_POS), 'O', 'D'), pos=d.pos_abb,
                         dt=pd.to_datetime(d.dt, utc=True), week=np.nan)
            out.append(d[['season', 'team', 'week', 'gsis_id', 'side', 'pos', 'dt']].dropna(subset=['gsis_id']))
    return pd.concat(out, ignore_index=True)


def extras():
    p = os.path.join(CACHE, 'extras.pkl')
    if os.path.exists(p):
        return pd.read_pickle(p)
    g = schedule()
    g['kick'] = pd.to_datetime(g.gameday + ' ' + g.gametime.fillna('13:00'), errors='coerce').dt.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC')
    side = pd.concat([g.assign(team=g.home_team, is_home=1, rest=g.rest_h), g.assign(team=g.away_team, is_home=0, rest=g.rest_a)])
    side = side[['game_id', 'season', 'week', 'kick', 'team', 'is_home', 'rest']]
    # QB: first-dropback starter, shrunk earlier EPA, starts, change vs previous game
    pb = data.nfl_pbp(range(2006, 2027))
    db = pb[(pb.qb_dropback == 1) & pb.passer_player_id.notna() & pb.posteam.notna()].copy()
    db = db.sort_values(['game_id', 'play_id'])
    first = db.drop_duplicates(['game_id', 'posteam'])[['game_id', 'posteam', 'passer_player_id', 'passer_player_name']]
    q = db.groupby(['game_id', 'posteam', 'passer_player_id']).agg(n=('epa', 'size'), epa=('epa', 'sum')).reset_index()
    q = q.merge(g[['game_id', 'kick']], on='game_id').sort_values('kick')
    q['cum_n'] = q.groupby('passer_player_id').n.cumsum() - q.n
    q['cum_epa'] = q.groupby('passer_player_id').epa.cumsum() - q.epa
    st = q.merge(first, on=['game_id', 'posteam', 'passer_player_id']).sort_values('kick')
    st['starts_before'] = st.groupby('passer_player_id').cumcount()
    st['qb_value'] = st.cum_epa / (st.cum_n + 200)
    st['backup_qb'] = (st.starts_before < 4).astype(float)
    st['prev'] = st.groupby('posteam').passer_player_id.shift()
    st['qb_change'] = (st.prev.notna() & (st.prev != st.passer_player_id)).astype(float)
    side = side.merge(st[['game_id', 'posteam', 'passer_player_name', 'qb_value', 'backup_qb', 'qb_change']]
                      .rename(columns={'posteam': 'team', 'passer_player_name': 'qb'}), on=['game_id', 'team'], how='left')
    side['qb_value'] = side.qb_value.fillna(0.0); side['backup_qb'] = side.backup_qb.fillna(1.0); side['qb_change'] = side.qb_change.fillna(0.0)
    # injuries: starters (previous depth chart) listed Out/Doubtful, and Questionable, by side (QB excluded: QB terms above)
    S = _starters()
    inj = data.nfl_injuries(range(2009, 2027))[['season', 'team', 'week', 'gsis_id', 'report_status']].dropna(subset=['gsis_id'])
    old = S[S.dt.isna()]; new = S[S.dt.notna()]
    cnt = []
    for (y, t), x in side[side.season >= 2009].groupby(['season', 'team']):
        if y <= 2024:
            o = old[(old.season == y) & (old.team == t)]
            weeks = sorted(o.week.dropna().unique())
        for _, r in x.iterrows():
            if y <= 2024:
                prev = [w for w in weeks if w < r.week] or [w for w in weeks if w == r.week]
                if not prev:
                    continue
                stt = o[o.week == prev[-1]]
            else:
                nn = new[(new.season == y) & (new.team == t) & (new.dt <= r.kick - pd.Timedelta(days=6))]
                if nn.empty:
                    nn = new[(new.season == y) & (new.team == t) & (new.dt <= r.kick)]
                if nn.empty:
                    continue
                stt = nn[nn.dt == nn.dt.max()]
            stt = stt[stt.pos != 'QB'].drop_duplicates('gsis_id')
            ij = inj[(inj.season == y) & (inj.team == t) & (inj.week == r.week)]
            m = stt.merge(ij, on='gsis_id')
            out_ = m.report_status.isin(['Out', 'Doubtful']); qq = m.report_status.eq('Questionable')
            cnt.append(dict(game_id=r.game_id, team=t, off_out=float((out_ & (m.side == 'O')).sum()), def_out=float((out_ & (m.side == 'D')).sum()),
                            off_q=float((qq & (m.side == 'O')).sum()), def_q=float((qq & (m.side == 'D')).sum())))
    side = side.merge(pd.DataFrame(cnt), on=['game_id', 'team'], how='left')
    for c in ('off_out', 'def_out', 'off_q', 'def_q'):
        side[c] = side[c].fillna(0.0)
    h = side[side.is_home == 1].set_index('game_id'); a = side[side.is_home == 0].set_index('game_id').reindex(h.index)
    out = pd.DataFrame(index=h.index)
    for x in EXTRA:
        out[f'm_{x}'] = h[x] - a[x]; out[f't_{x}'] = h[x] + a[x]
    out['home_qb'] = h.qb; out['away_qb'] = a.qb
    out = out.reset_index()
    os.makedirs(CACHE, exist_ok=True); out.to_pickle(p)
    return out


# ---------------------------------------------------------------- model
def design(f, kind):
    if kind == 'margin':
        cols = ['spread_home', 'neutral', 'div'] + [f'm_{s}' for s in STATS] + [f'm_{x}' for x in EXTRA]
        if LINE_FREE:
            cols = cols[1:]                                   # amendment 12: no line
    else:
        cols = ['total_line'] + GAME + [f't_{s}' for s in STATS] + [f't_{x}' for x in EXTRA]
        if LINE_FREE:
            cols = cols[1:]
    X = f[cols].astype(float).copy()
    if kind == 'margin' and 'spread_home' in X:
        X['spread_home'] = -X['spread_home']
    X.insert(0, 'const', 1.0)
    return X


def fit(f, kind):
    y = f.result if kind == 'margin' else f.total
    X = design(f, kind); ok = X.notna().all(axis=1) & y.notna()
    if kind == 'total' and TOTAL_MODE == 'median' and ok.any():          # amendment 14 M
        from sklearn.linear_model import QuantileRegressor
        q = QuantileRegressor(quantile=0.5, alpha=0.0, fit_intercept=False, solver='highs').fit(X[ok].values, y[ok].values)
        b = q.coef_
    elif kind == 'total' and TOTAL_MODE == 'offset' and 'total_line' in X and ok.any():   # amendment 14 O
        Xo = X.drop(columns='total_line')
        bo, *_ = np.linalg.lstsq(Xo[ok].values, (y - X['total_line'])[ok].values, rcond=None)
        b = pd.Series(bo, Xo.columns).reindex(X.columns).fillna(1.0).values
    else:
        b, *_ = np.linalg.lstsq(X[ok].values, y[ok].values, rcond=None)
    return pd.Series(b, X.columns), float(np.std(y[ok].values - X[ok].values @ b))


def walk_forward(f):
    f = f.copy(); f['pm'] = np.nan; f['pt'] = np.nan; f['sd'] = np.nan
    for S in range(FIRST_FIT + 1, 2027):
        tr, te = f[f.season.between(FIRST_FIT, S - 1)], f.season == S
        bm, sd = fit(tr, 'margin'); bt, _ = fit(tr, 'total')
        f.loc[te, 'pm'] = design(f[te], 'margin').values @ bm.values
        f.loc[te, 'pt'] = design(f[te], 'total').values @ bt.values
        f.loc[te, 'sd'] = sd
    return f


def _rate(w, n):
    return w / n if n else float('nan')


def bets(f, period, kind, thr):
    x = f[f.season.between(*period) & f.result.notna() & f.pm.notna()]
    if kind == 'spread':
        edge = x.pm - x.spread_line; res = x.result - x.spread_line
    else:
        edge = x.pt - x.total_line; res = x.total - x.total_line
    pick = edge > 0
    win = np.where(pick, res > 0, res < 0); ok = (edge.abs() >= thr) & (res != 0) & edge.notna()
    return int(win[ok.values].sum()), int(ok.sum()), float(pick[ok].mean()) if ok.any() else float('nan')


def winner_bets(f, period):
    from math import erf, sqrt
    x = f[f.season.between(*period) & f.result.notna() & f.pm.notna() & f.home_moneyline.notna() & f.away_moneyline.notna()]
    ph = np.array([0.5 * (1 + erf(m / (s * sqrt(2)))) for m, s in zip(x.pm, x.sd)])
    be = lambda ml: np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100))
    vh, va = ph - be(x.home_moneyline.values), (1 - ph) - be(x.away_moneyline.values)
    bh = vh >= 0.03; ba = (va >= 0.03) & ~bh
    hw = (x.result > 0).values; push = (x.result == 0).values
    prof = np.concatenate([np.where(hw[bh & ~push], ml_profit(x.home_moneyline.values[bh & ~push]), -1.0),
                           np.where(~hw[ba & ~push], ml_profit(x.away_moneyline.values[ba & ~push]), -1.0)])
    return int(hw[bh & ~push].sum() + (~hw[ba & ~push]).sum()), len(prof), prof


def rules(f, period):
    """Carry-over rules re-tested with no model: T teaser legs, P price gap, W wind Under."""
    from statistics import NormalDist
    x = f[f.season.between(*period) & f.result.notna()]
    out = {}
    # T: dog +1.5..+2.5 teased 6 -> covers if dog margin + points + 6 > 0
    hd = x.spread_line.between(-2.5, -1.5); ad = x.spread_line.between(1.5, 2.5)
    rh = x.result[hd] - x.spread_line[hd] + 6; ra = -(x.result[ad] - x.spread_line[ad]) + 6
    r = pd.concat([rh, ra]); r = r[r != 0]
    out['T'] = (int((r > 0).sum()), int(len(r)))
    # P: no-vig moneyline home chance -> implied margin (SD fixed from 2006-2010, before every test period)
    ok = x.home_moneyline.notna() & x.away_moneyline.notna()
    be = lambda ml: np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100))
    y = x[ok]; ph = be(y.home_moneyline.values); pa = be(y.away_moneyline.values); pnv = ph / (ph + pa)
    imp = np.array([SD_IMPLIED * NormalDist().inv_cdf(min(max(p, 1e-6), 1 - 1e-6)) for p in pnv])
    gap = imp - y.spread_line.values; res = (y.result - y.spread_line).values
    sel = (np.abs(gap) >= 1) & (res != 0)
    out['P'] = (int(np.where(gap > 0, res > 0, res < 0)[sel].sum()), int(sel.sum()))
    # W: game-book wind 15+ (outdoor, wind known) -> Under
    w = x[x.roof.isin(['outdoors', 'open']) & (x.wind >= 15)]
    rr = (w.total - w.total_line); rr = rr[rr != 0]
    out['W'] = (int((rr < 0).sum()), int(len(rr)))
    return out


g0 = data.nfl_schedules()
_w = g0[g0.season.between(2006, 2010) & g0.result.notna()]
SD_IMPLIED = float(np.std(_w.result - _w.spread_line))


if __name__ == '__main__':
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    txt = ['core NFL game model - walk-forward (core/PROTOCOL.md amendments 6-7). Every NFL season was used by old builds.']
    mse = {}
    for H in H_GRID:
        f = walk_forward(build(H))
        e = f[f.season.between(*EARLY) & f.result.notna() & f.pm.notna()]
        mse[H] = float(((e.pm - e.result) ** 2).mean() + ((e.pt - e.total) ** 2).mean())
        txt.append(f'H={H:2d}: EARLY MSE margin+total {mse[H]:.1f} ({len(e)} games)')
    H = min(mse, key=mse.get); txt.append(f'Chosen on EARLY only: H = {H}. LATE run once:\n')
    f = walk_forward(build(H))
    res = {}
    for kind in ('spread', 'total'):
        for thr in (0, 2, 4):
            e, l = bets(f, EARLY, kind, thr), bets(f, LATE, kind, thr)
            p = pval(e[0] + l[0], e[1] + l[1]); ok = e[1] >= 100 and l[1] >= 100 and _rate(*e[:2]) >= .524 and _rate(*l[:2]) >= .524 and p < .05
            res[f'{kind} edge {thr}+'] = dict(early=e[:2], late=l[:2], p=p, passes=ok)
            txt.append(f"{kind+' edge '+str(thr)+'+':15s} EARLY {e[0]}/{e[1]} = {_rate(*e[:2]):.1%} | LATE {l[0]}/{l[1]} = {_rate(*l[:2]):.1%} | p={p:.3f} | "
                       f"{'TESTED PICK' if ok else 'LEAN':11s} | {'home' if kind == 'spread' else 'Over'} picks {e[2]:.0%} / {l[2]:.0%}")
    we, wl = winner_bets(f, EARLY), winner_bets(f, LATE); allp = np.concatenate([we[2], wl[2]])
    t = allp.mean() / (allp.std(ddof=1) / math.sqrt(len(allp))); pw = 0.5 * math.erfc(t / math.sqrt(2))
    okw = we[1] >= 100 and wl[1] >= 100 and we[2].mean() > 0 and wl[2].mean() > 0 and pw < .05
    res['winner 3%+ value'] = dict(early=[we[0], we[1]], late=[wl[0], wl[1]], early_roi=float(we[2].mean()), late_roi=float(wl[2].mean()), p=pw, passes=okw)
    txt.append(f"{'winner 3%+ val':15s} EARLY {we[0]}/{we[1]} ROI {we[2].mean():+.1%} | LATE {wl[0]}/{wl[1]} ROI {wl[2].mean():+.1%} | p={pw:.3f} | {'TESTED PICK' if okw else 'LEAN'}")
    txt.append(f'\nCarry-over rules (no model; implied-margin SD {SD_IMPLIED:.2f} from 2006-10):')
    re_, rl = rules(f, EARLY), rules(f, LATE)
    for k, name, need in (('T', 'T teaser leg, dog +1.5..+2.5', .739), ('P', 'P price gap 1+ pt', .524), ('W', 'W Under, wind 15+', .524)):
        e, l = re_[k], rl[k]; p = pval(e[0] + l[0], e[1] + l[1], need)
        ok = e[1] >= 100 and l[1] >= 100 and _rate(*e) >= need and _rate(*l) >= need and p < .05
        res[k] = dict(early=e, late=l, p=p, passes=ok)
        txt.append(f"  {name:30s} EARLY {e[0]}/{e[1]} = {_rate(*e):.1%} | LATE {l[0]}/{l[1]} = {_rate(*l):.1%} | needs {need:.1%} | p={p:.3f} | {'TESTED PICK' if ok else 'FAIL'}")
    e = f[f.season.between(*EARLY) & f.result.notna() & f.pm.notna()]
    def mse_cols(cm, ct):
        out = []
        for S in range(EARLY[0], EARLY[1] + 1):
            tr, te = f[f.season.between(FIRST_FIT, S - 1)], f[(f.season == S) & f.result.notna()]
            for cols, y, yt in ((cm, tr.result, te.result), (ct, tr.total, te.total)):
                X = tr[cols].astype(float).assign(c=1.0); Xt = te[cols].astype(float).assign(c=1.0)
                ok = X.notna().all(1) & y.notna(); okt = Xt.notna().all(1)
                b, *_ = np.linalg.lstsq(X[ok].values, y[ok].values, rcond=None)
                out.append(((Xt[okt].values @ b - yt[okt].values) ** 2).mean())
        return np.mean(out[0::2]), np.mean(out[1::2])
    lo = mse_cols(['spread_line', 'neutral'], ['total_line'])
    txt.append(f"\nEARLY squared error, margin / total: line only {lo[0]:.1f} / {lo[1]:.1f}; full model "
               f"{((e.pm - e.result) ** 2).mean():.1f} / {((e.pt - e.total) ** 2).mean():.1f}")
    bm, _ = fit(f[f.season.between(FIRST_FIT, 2025)], 'margin'); bt, _ = fit(f[f.season.between(FIRST_FIT, 2025)], 'total')
    txt.append('\nweights (fit 2009-2025): margin ' + ', '.join(f'{k} {v:+.3f}' for k, v in bm.items()))
    txt.append('                          total  ' + ', '.join(f'{k} {v:+.3f}' for k, v in bt.items()))
    open(os.path.join(HERE, 'results', 'nfl_test.txt'), 'w').write('\n'.join(txt) + '\n')
    json.dump(dict(H=H, mse=mse, results=res), open(os.path.join(HERE, 'results', 'nfl_test.json'), 'w'), indent=1, default=float)
    print('\n'.join(txt))
