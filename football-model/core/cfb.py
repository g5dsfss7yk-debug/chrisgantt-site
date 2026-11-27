"""core college game model (core/PROTOCOL.md). Standalone.
python core/cfb.py test      -> walk-forward test, picks H on EARLY, runs LATE once -> core/results/cfb_test.txt/json
python core/cfb.py freeze    -> fits the final model on every finished season -> core/frozen_cfb.json"""
import os, sys, json, math
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data

STATS = ['pass_epa', 'rush_epa', 'success', 'turnovers', 'sack_rate', 'explosive', 'return_td', 'plays']
H_GRID = (4, 8, 16)
LAMBDA = 5.0
FIRST, EARLY, LATE = 2015, (2017, 2022), (2023, 2026)
CACHE = os.path.join(data.DATA, 'cfb')
EXTRA = []          # amendment 2 variables, set by 'test2'
OUTNAME = 'cfb_test2_firstqb'   # amendment 5 re-run (the leaky run is saved as cfb_test2.txt)
EXTRA_ALL = ['qb_value', 'backup_qb', 'qb_change', 'elo', 'talent', 'returning', 'rest', 'travel']


# ---------------------------------------------------------------- per team-game stats (offense's plays)
def team_games(seasons):
    p = data.cfb_pbp(seasons)
    rt = p.play_type.isin(data.RETURN_TD)
    scr = ((p['rush'] == 1) | (p['pass'] == 1) | rt) & p.pos_team.notna() & p.def_pos_team.notna()
    p = p[scr & p.wp_before.between(0.05, 0.95)].copy()
    p['to'] = ((p.turnover == 1) | rt).astype(float)         # fumble-return TDs are not always flagged turnover
    p['db'] = (p['pass'] == 1).astype(float)
    p['ru'] = ((p['rush'] == 1) & (p['pass'] != 1)).astype(float)
    p['ex'] = (p.yards_gained >= 20).astype(float)
    p['sk'] = (p.sack == 1).astype(float)
    p['pe'] = p.EPA.where(p.db == 1); p['re'] = p.EPA.where(p.ru == 1)
    g = p.groupby(['game_id', 'pos_team']).agg(
        season=('season', 'first'), week=('week', 'first'), season_type=('season_type', 'first'), date=('start_date', 'first'),
        defteam=('def_pos_team', 'first'), home=('home', 'first'), away=('away', 'first'), neutral=('neutral_site', 'first'),
        pass_epa=('pe', 'mean'), rush_epa=('re', 'mean'), success=('success', 'mean'), turnovers=('to', 'sum'),
        sacks=('sk', 'sum'), dropbacks=('db', 'sum'), explosive=('ex', 'mean'), return_td=('return_td', 'sum'), plays=('EPA', 'size'))
    g['sack_rate'] = g.sacks / g.dropbacks.where(g.dropbacks > 0)
    g = g.reset_index().rename(columns={'pos_team': 'team'})
    g['loc'] = np.where(g.neutral.fillna(False).astype(bool), 0, np.where(g.team == g.home, 1, -1))
    g['date'] = pd.to_datetime(g.date, utc=True)
    return g


def slates(tg):
    """Ordered slates (season, season_type, week) with their first kickoff; postseason is one slate per season."""
    s = tg.assign(wk=np.where(tg.season_type == 'postseason', 99, tg.week)).groupby(['season', 'wk']).date.min().sort_values()
    return s.reset_index()


# ---------------------------------------------------------------- opponent-adjusted ratings
def ratings_for_slate(hist, H, idx_now):
    """Ridge: stat ~ offense team + defense team + home, weights 0.5^(slates ago / H), last two seasons."""
    import scipy.sparse as sp
    teams = pd.Index(sorted(set(hist.team) | set(hist.defteam)))
    n, k = len(hist), len(teams)
    oi, di = teams.get_indexer(hist.team), teams.get_indexer(hist.defteam)
    w = 0.5 ** ((idx_now - hist.slate_i.values) / H)
    rows = np.repeat(np.arange(n), 3)
    cols = np.column_stack([oi, k + di, np.full(n, 2 * k)]).ravel()
    vals = np.column_stack([np.ones(n), np.ones(n), hist['loc'].values.astype(float)]).ravel()
    X = sp.csr_matrix((vals, (rows, cols)), shape=(n, 2 * k + 1))
    pen = np.full(2 * k + 1, LAMBDA); pen[-1] = 1e-6
    out, cacheA = {}, {}
    for s in STATS:
        y = hist[s].values.astype(float); ok = ~np.isnan(y)
        key = ok.tobytes() if not ok.all() else b'all'
        wo = np.where(ok, w, 0.0)
        if key not in cacheA:
            cacheA[key] = (X.T @ sp.diags(wo) @ X).toarray() + np.diag(pen)
        mu = np.average(y[ok], weights=w[ok])
        r = np.where(ok, y - mu, 0.0)
        b = np.linalg.solve(cacheA[key], X.T @ (wo * r))
        out[s] = (mu, pd.Series(b[:k], teams), pd.Series(b[k:2 * k], teams), b[-1])
    return out


def build(H, seasons=range(2014, 2027)):
    p = os.path.join(CACHE, f'features_H{H}.pkl')
    if os.path.exists(p):
        return pd.read_pickle(p)
    tg = team_games(seasons)
    sl = slates(tg)
    tg['wk'] = np.where(tg.season_type == 'postseason', 99, tg.week)
    tg = tg.merge(sl[['season', 'wk']].reset_index().rename(columns={'index': 'slate_i'}), on=['season', 'wk'])
    games = tg[tg.team == tg.home][['game_id', 'season', 'season_type', 'week', 'date', 'home', 'away', 'neutral', 'slate_i']].drop_duplicates('game_id')
    games['neutral'] = games.neutral.fillna(False).astype(bool)
    rows = []
    for i, r in sl.iterrows():
        if r.season < FIRST:
            continue
        hist = tg[(tg.slate_i < i) & (tg.season >= r.season - 1)]
        if hist.empty:
            continue
        R = ratings_for_slate(hist, H, i)
        for _, gm in games[games.slate_i == i].iterrows():
            row = dict(game_id=gm.game_id)
            loc = 0 if bool(gm.neutral) else 1
            for s in STATS:
                mu, off, dfn, home = R[s]
                he = mu + off.get(gm.home, 0.0) + dfn.get(gm.away, 0.0) + home * loc
                ae = mu + off.get(gm.away, 0.0) + dfn.get(gm.home, 0.0) - home * loc
                row[f'm_{s}'] = he - ae; row[f't_{s}'] = he + ae
            row['known_h'] = int(gm.home in off.index); row['known_a'] = int(gm.away in off.index)
            rows.append(row)
    f = games.merge(pd.DataFrame(rows), on='game_id')
    f = f.merge(lines(seasons), on='game_id', how='left')
    os.makedirs(CACHE, exist_ok=True); f.to_pickle(p)
    return f


def lines(seasons):
    L = data.cfb_lines(seasons)
    med = L.groupby('game_id').agg(spread_med=('spread', 'median'), total_med=('total', 'median'),
                                   hml_med=('home_ml', 'median'), aml_med=('away_ml', 'median'),
                                   home_score=('home_score', 'first'), away_score=('away_score', 'first'))
    dk = L[L.provider == 'DraftKings'].groupby('game_id').agg(spread_dk=('spread', 'first'), total_dk=('total', 'first'),
                                                               hml_dk=('home_ml', 'first'), aml_dk=('away_ml', 'first'),
                                                               spread_dk_open=('spread_open', 'first'), total_dk_open=('total_open', 'first'))
    return med.join(dk).reset_index()


# ---------------------------------------------------------------- amendment 2 variables (QB, Elo, talent, returning, rest, travel)
def extras(seasons=range(2014, 2027)):
    p = os.path.join(CACHE, 'extras.pkl')
    if os.path.exists(p):
        return pd.read_pickle(p)
    pb = data.cfb_pbp(seasons)
    gm = pb.groupby('game_id').agg(season=('season', 'first'), week=('week', 'first'), st=('season_type', 'first'),
                                   date=('start_date', 'first'), home=('home', 'first'), away=('away', 'first'),
                                   venue_id=('venue_id', 'first'), helo=('home_team_pregame_elo', 'first'),
                                   aelo=('away_team_pregame_elo', 'first')).reset_index()
    gm['date'] = pd.to_datetime(gm.date, utc=True)
    side = pd.concat([gm.assign(team=gm.home, elo=gm.helo, is_home=1), gm.assign(team=gm.away, elo=gm.aelo, is_home=0)])
    side = side[['game_id', 'season', 'week', 'st', 'date', 'venue_id', 'team', 'elo', 'is_home']].sort_values(['team', 'date'])
    # Elo: missing -> team's most recent earlier Elo, else season's lowest
    side['elo'] = side.groupby('team').elo.ffill()
    side['elo'] = side.elo.fillna(side.groupby('season').elo.transform('min'))
    # rest: days since previous game, cap 14; first game of a season = 14
    prev = side.groupby('team').date.shift(); prevs = side.groupby('team').season.shift()
    side['rest'] = ((side.date - prev).dt.total_seconds() / 86400).where(prevs == side.season).clip(upper=14).fillna(14)
    # talent (season, team): missing -> season's lowest
    t = data.cfb_talent(seasons)
    side = side.merge(t, on=['season', 'team'], how='left')
    side['talent'] = side.talent.fillna(side.groupby('season').talent.transform('min'))
    # returning production faded by week 6 (postseason -> 0); missing -> season mean
    r = data.cfb_returning(seasons)
    side = side.merge(r, on=['season', 'team'], how='left')
    side['returning'] = side.returning.clip(0, 1)                                 # amendment 4
    side['returning'] = side.returning.fillna(side.groupby('season').returning.transform('mean'))
    fade = np.where(side.st == 'postseason', 0.0, np.clip(1 - (side.week - 1) / 5, 0, 1))
    side['returning'] = side.returning.fillna(0) * fade
    # travel: team's home stadium -> game venue, miles / 1000; missing -> 0
    th = data.cfb_team_home().dropna(subset=['tlat']).drop_duplicates('team')
    v = data.cfb_venues().dropna(subset=['vlat'])
    side = side.merge(th, on='team', how='left').merge(v[['venue_id', 'vlat', 'vlon']], on='venue_id', how='left')
    la1, lo1, la2, lo2 = (np.radians(side[c].astype(float)) for c in ('tlat', 'tlon', 'vlat', 'vlon'))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    side['travel'] = (3958.8 * 2 * np.arcsin(np.sqrt(a)) / 1000).fillna(0.0)
    # QB: starter = most dropbacks; value = shrunk earlier dropback EPA; backup < 4 earlier starts; change vs last game
    db = pb[(pb['pass'] == 1) & pb.passer_player_name.notna() & pb.pos_team.notna()]
    db = db.assign(order=np.arange(len(db)))                          # play-by-play is in game order
    first = db.sort_values('order').drop_duplicates(['game_id', 'pos_team'])[['game_id', 'pos_team', 'passer_player_name']]
    q = db.groupby(['game_id', 'pos_team', 'passer_player_name']).agg(n=('EPA', 'size'), epa=('EPA', 'sum')).reset_index()
    q = q.merge(gm[['game_id', 'date']], on='game_id').sort_values('date')
    q['cum_n'] = q.groupby('passer_player_name').n.cumsum() - q.n
    q['cum_epa'] = q.groupby('passer_player_name').epa.cumsum() - q.epa
    # amendment 5: starter = QB on the team's FIRST dropback (known at kickoff), not the one with most dropbacks
    st_ = q.merge(first, on=['game_id', 'pos_team', 'passer_player_name']).sort_values('date')
    st_['starts_before'] = st_.groupby('passer_player_name').cumcount()
    st_['qb_value'] = st_.cum_epa / (st_.cum_n + 200)
    st_['backup_qb'] = (st_.starts_before < 4).astype(float)
    st_['prev_qb'] = st_.groupby('pos_team').passer_player_name.shift()
    st_['qb_change'] = ((st_.prev_qb.notna()) & (st_.prev_qb != st_.passer_player_name)).astype(float)
    side = side.merge(st_[['game_id', 'pos_team', 'passer_player_name', 'qb_value', 'backup_qb', 'qb_change']]
                      .rename(columns={'pos_team': 'team', 'passer_player_name': 'qb'}), on=['game_id', 'team'], how='left')
    side['qb_value'] = side.qb_value.fillna(0.0); side['backup_qb'] = side.backup_qb.fillna(1.0); side['qb_change'] = side.qb_change.fillna(0.0)
    h = side[side.is_home == 1].set_index('game_id'); a_ = side[side.is_home == 0].set_index('game_id')
    out = pd.DataFrame(index=h.index)
    for x in EXTRA_ALL:
        out[f'm_{x}'] = h[x] - a_[x].reindex(h.index)
        out[f't_{x}'] = h[x] + a_[x].reindex(h.index)
    out['home_qb'] = h.qb; out['away_qb'] = a_.qb.reindex(h.index)
    out = out.reset_index()
    out.to_pickle(p)
    return out


# ---------------------------------------------------------------- game model
def design(f, kind):
    if kind == 'margin':
        cols = ['spread_med', 'neutral'] + [f'm_{s}' for s in STATS] + [f'm_{x}' for x in EXTRA]
    else:
        cols = ['total_med'] + [f't_{s}' for s in STATS] + [f't_{x}' for x in EXTRA]
    X = f[cols].astype(float).copy()
    if kind == 'margin':
        X['spread_med'] = -X['spread_med']           # home number -> expected home margin by the line
    X.insert(0, 'const', 1.0)
    return X


def fit(f, kind):
    y = (f.home_score - f.away_score) if kind == 'margin' else (f.home_score + f.away_score)
    X = design(f, kind); ok = X.notna().all(axis=1) & y.notna()
    b, *_ = np.linalg.lstsq(X[ok].values, y[ok].values, rcond=None)
    sd = float(np.std(y[ok].values - X[ok].values @ b))
    return pd.Series(b, X.columns), sd


def predict(f, b, kind):
    X = design(f, kind)
    return pd.Series(X.values @ b.values, f.index)


def walk_forward(f):
    f = f.copy(); f['pm'] = np.nan; f['pt'] = np.nan; f['sd'] = np.nan
    for S in range(FIRST + 1, 2027):
        tr, te = f[(f.season < S) & (f.season >= FIRST)], f.season == S
        if tr.empty or not te.any():
            continue
        bm, sd = fit(tr, 'margin'); bt_, _ = fit(tr, 'total')
        f.loc[te, 'pm'] = predict(f[te], bm, 'margin'); f.loc[te, 'pt'] = predict(f[te], bt_, 'total'); f.loc[te, 'sd'] = sd
    return f


# ---------------------------------------------------------------- grading (fixed in PROTOCOL)
def _line(f, period, kind):
    late = period == LATE
    if kind == 'spread':
        return f.spread_dk if late else f.spread_med
    if kind == 'total':
        return f.total_dk if late else f.total_med


def bets(f, period, kind, thr):
    x = f[f.season.between(*period) & f.home_score.notna()].copy()
    ln = _line(x, period, kind)
    if kind == 'spread':
        exp = -ln; edge = x.pm - exp
        res = (x.home_score - x.away_score) + ln            # > 0 home covers
        pick_home = edge > 0
        win = np.where(pick_home, res > 0, res < 0); push = res == 0
    else:
        edge = x.pt - ln
        res = (x.home_score + x.away_score) - ln
        pick_home = edge > 0                                   # Over
        win = np.where(pick_home, res > 0, res < 0); push = res == 0
    ok = ln.notna() & x.pm.notna() & (edge.abs() >= thr) & ~push
    return int(win[ok.values].sum()), int(ok.sum()), float(pick_home[ok].mean()) if ok.any() else float('nan')


def ml_profit(ml):
    return np.where(ml > 0, ml / 100, 100 / -ml)


def winner_bets(f, period):
    from math import erf, sqrt
    x = f[f.season.between(*period) & f.home_score.notna() & f.pm.notna()].copy()
    late = period == LATE
    hml, aml = (x.hml_dk, x.aml_dk) if late else (x.hml_med, x.aml_med)
    ph = pd.Series([0.5 * (1 + erf(m / (s * sqrt(2)))) for m, s in zip(x.pm, x.sd)], x.index)
    be = lambda ml: np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100))
    ok = hml.notna() & aml.notna() & (hml != 0) & (aml != 0)
    x, ph, hml, aml = x[ok], ph[ok], hml[ok], aml[ok]
    vh, va = ph - be(hml), (1 - ph) - be(aml)
    bet_h, bet_a = vh >= 0.03, (va >= 0.03) & ~(vh >= 0.03)
    hw = x.home_score > x.away_score
    prof = np.concatenate([np.where(hw[bet_h], ml_profit(hml[bet_h]), -1.0), np.where(~hw[bet_a], ml_profit(aml[bet_a]), -1.0)])
    wins = int(hw[bet_h].sum() + (~hw[bet_a]).sum())
    return wins, len(prof), prof


def pval(w, n, p0=0.524):
    if n == 0:
        return 1.0
    from math import comb
    # one-sided binomial P(X >= w | n, p0) via normal approximation for large n, exact for small n
    if n > 400:
        z = (w - n * p0 - 0.5) / math.sqrt(n * p0 * (1 - p0))
        return 0.5 * math.erfc(z / math.sqrt(2))
    return sum(comb(n, k) * p0 ** k * (1 - p0) ** (n - k) for k in range(w, n + 1))


def report(f):
    out, lines_ = {}, []
    for kind in ('spread', 'total'):
        for thr in (0, 2, 4):
            e, l = bets(f, EARLY, kind, thr), bets(f, LATE, kind, thr)
            p = pval(e[0] + l[0], e[1] + l[1])
            ok = e[1] >= 100 and l[1] >= 100 and e[0] / max(e[1], 1) >= 0.524 and l[0] / max(l[1], 1) >= 0.524 and p < 0.05
            key = f'{kind} edge {thr}+'
            out[key] = dict(early=e[:2], late=l[:2], p=p, passes=ok, early_side=e[2], late_side=l[2])
            side = 'home' if kind == 'spread' else 'Over'
            lines_.append(f"{key:15s} EARLY {e[0]}/{e[1]} = {e[0]/max(e[1],1):.1%} | LATE {l[0]}/{l[1]} = {l[0]/max(l[1],1):.1%} | p={p:.3f} | "
                          f"{'TESTED PICK' if ok else 'LEAN':11s} | {side} picks {e[2]:.0%} / {l[2]:.0%}")
    we, wl = winner_bets(f, EARLY), winner_bets(f, LATE)
    def tstat(pr):
        return float(pr.mean() / (pr.std(ddof=1) / math.sqrt(len(pr)))) if len(pr) > 2 else 0.0
    allp = np.concatenate([we[2], wl[2]])
    pw = 0.5 * math.erfc(tstat(allp) / math.sqrt(2)) if len(allp) > 2 else 1.0
    okw = we[1] >= 100 and wl[1] >= 100 and we[2].mean() > 0 and wl[2].mean() > 0 and pw < 0.05
    out['winner 3%+ value'] = dict(early=[we[0], we[1]], late=[wl[0], wl[1]], early_roi=float(we[2].mean()) if we[1] else None,
                                   late_roi=float(wl[2].mean()) if wl[1] else None, p=pw, passes=okw)
    lines_.append(f"{'winner 3%+ val':15s} EARLY {we[0]}/{we[1]} ROI {we[2].mean():+.1%} | LATE {wl[0]}/{wl[1]} ROI {wl[2].mean():+.1%} | "
                  f"p={pw:.3f} | {'TESTED PICK' if okw else 'LEAN'}")
    return out, lines_


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'test'
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    if cmd == 'test':
        txt = ['core college game model - walk-forward (core/PROTOCOL.md)']
        mse = {}
        for H in H_GRID:
            f = walk_forward(build(H))
            e = f[f.season.between(*EARLY) & f.home_score.notna() & f.pm.notna() & f.pt.notna()]
            mse[H] = float(((e.pm - (e.home_score - e.away_score)) ** 2).mean() + ((e.pt - (e.home_score + e.away_score)) ** 2).mean())
            txt.append(f'H={H:2d}: EARLY MSE margin+total {mse[H]:.1f} ({len(e)} games)')
        H = min(mse, key=mse.get)
        txt.append(f'Chosen on EARLY only: H = {H}. LATE run once with it:\n')
        f = walk_forward(build(H))
        out, ln = report(f)
        txt += ln
        bm, sdm = fit(f[f.season.between(FIRST, 2025)], 'margin'); bt_, sdt = fit(f[f.season.between(FIRST, 2025)], 'total')
        txt.append('\nweights (fit 2015-2025): margin ' + ', '.join(f'{k} {v:+.3f}' for k, v in bm.items()))
        txt.append('                          total  ' + ', '.join(f'{k} {v:+.3f}' for k, v in bt_.items()))
        open(os.path.join(HERE, 'results', 'cfb_test.txt'), 'w').write('\n'.join(txt) + '\n')
        json.dump(dict(H=H, mse=mse, results=out), open(os.path.join(HERE, 'results', 'cfb_test.json'), 'w'), indent=1, default=float)
        print('\n'.join(txt))
    if cmd == 'test2':
        H = json.load(open(os.path.join(HERE, 'results', 'cfb_test.json')))['H']
        base = build(H)
        X = extras()
        f = base.merge(X, on='game_id', how='left')
        for x in EXTRA_ALL:
            f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)   # talent: 2014 warm-up only
        txt = [f'core college game model + amendment 2 variables (H = {H} from the first run). LATE 2023-26 was seen once before.']
        f0 = walk_forward(f)
        _, ln0 = report(f0)
        EXTRA[:] = EXTRA_ALL
        f2 = walk_forward(f)
        out, ln = report(f2)
        txt.append('\nFIRST RUN (8 stats + line), same games:'); txt += ln0
        txt.append('\nWITH ALL VARIABLES (8 stats + QB, Elo, talent, returning, rest, travel + line):'); txt += ln
        e = lambda g: g[g.season.between(*EARLY) & g.home_score.notna() & g.pm.notna() & g.pt.notna()]
        for name, g in (('first run', f0), ('all variables', f2)):
            x = e(g)
            txt.append(f"EARLY MSE {name}: margin {((x.pm - (x.home_score - x.away_score)) ** 2).mean():.1f}, total {((x.pt - (x.home_score + x.away_score)) ** 2).mean():.1f}")
        bm, _ = fit(f2[f2.season.between(FIRST, 2025)], 'margin'); bt_, _ = fit(f2[f2.season.between(FIRST, 2025)], 'total')
        txt.append('\nweights (fit 2015-2025): margin ' + ', '.join(f'{k} {v:+.3f}' for k, v in bm.items()))
        txt.append('                          total  ' + ', '.join(f'{k} {v:+.3f}' for k, v in bt_.items()))
        open(os.path.join(HERE, 'results', OUTNAME + '.txt'), 'w').write('\n'.join(txt) + '\n')
        json.dump(dict(H=H, results=out), open(os.path.join(HERE, 'results', OUTNAME + '.json'), 'w'), indent=1, default=float)
        print('\n'.join(txt))
