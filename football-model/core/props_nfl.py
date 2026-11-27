"""core NFL props (core/PROTOCOL.md amendment 9). Standalone (core/ only).
python core/props_nfl.py test   -> chooses HP on EARLY, fits on EARLY, checks LATE + DK price log -> core/results/props_nfl.txt"""
import os, sys, re, json, math
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import data, nfl

STATS = {'passing_yards': ['QB'], 'rushing_yards': ['RB', 'QB'], 'receiving_yards': ['WR', 'TE', 'RB'],
         'receptions': ['WR', 'TE', 'RB'], 'anytime_td': ['RB', 'WR', 'TE']}
ADJ = ['opp', 'tt', 'key_out', 'rb_out', 'quest', 'backup', 'wind_x', 'cold_x', 'wx_missing', 'dome']
HP_GRID = (4, 8, 16)
LINE_FLOOR = {'rushing_yards': 1.5, 'receiving_yards': 3.5, 'receptions': 1.5}   # amendment 10 (DK's smallest logged lines)
EARLY, LATE = (2014, 2019), (2020, 2026)
POS = ['QB', 'RB', 'FB', 'WR', 'TE']
CACHE = os.path.join(data.DATA, 'nfl')


def toks(s):
    return re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', re.sub(r"[^a-z ]", '', str(s).lower().replace('-', ' ').replace('.', ' '))).split()


def player_games():
    """Every offensive player-game with 1+ snap (weekly stats joined to snap counts; no stats = 0)."""
    p = os.path.join(CACHE, 'player_games.pkl')
    if os.path.exists(p):
        return pd.read_pickle(p)
    w = data.nfl_weekly(range(2013, 2027)); s = data.nfl_snaps(range(2013, 2027))
    w = w[w.position.isin(POS) & w.season_type.eq('REG')].copy()
    s = s[s.position.isin(POS) & (s.offense_snaps > 0) & s.game_type.eq('REG')].copy()
    w['anytime_td'] = (w.rushing_tds.fillna(0) + w.receiving_tds.fillna(0) > 0).astype(float)
    for d, c in ((w, 'player_display_name'), (s, 'player')):
        t = d[c].map(toks); d['k1'] = t.map(' '.join); d['k2'] = t.map(lambda x: (x[0][0] + ' ' + x[-1]) if x else '')
    keep = ['game_id', 'season', 'week', 'player_id', 'player_display_name', 'position', 'team', 'opponent_team', 'k1', 'k2',
            'passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'targets', 'carries', 'anytime_td']
    w = w[keep]
    used = set(zip(w.game_id, w.k1)) | set(zip(w.game_id, w.k2))
    z = s[[(g, a) not in used and (g, b) not in used for g, a, b in zip(s.game_id, s.k1, s.k2)]]
    sch = nfl.schedule()[['game_id', 'home_team', 'away_team']]
    z = z.merge(sch, on='game_id', how='left')
    z = z.assign(player_id='snap:' + z.pfr_player_id.astype(str), player_display_name=z.player,
                 opponent_team=np.where(z.team == z.home_team, z.away_team, z.home_team))
    for c in ('passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'targets', 'carries', 'anytime_td'):
        z[c] = 0.0
    # a snap-only player is linked to his stats id when the same name has one elsewhere (same team, season)
    ids = w.drop_duplicates(['k1', 'team', 'season']).set_index(['k1', 'team', 'season']).player_id
    z['player_id'] = [ids.get((a, t, y), pid) for a, t, y, pid in zip(z.k1, z.team, z.season, z.player_id)]
    pg = pd.concat([w, z[keep]], ignore_index=True)
    k = nfl.schedule()[['game_id', 'gameday', 'gametime']]
    pg = pg.merge(k, on='game_id', how='left')
    pg['kick'] = pd.to_datetime(pg.gameday + ' ' + pg.gametime.fillna('13:00'), errors='coerce')
    pg = pg.sort_values(['kick', 'game_id']).reset_index(drop=True)
    pg.to_pickle(p)
    return pg


def ew_before(df, key, col, HP):
    """Exponentially weighted mean of col over each key's EARLIER rows within the last two seasons (half-life HP rows)."""
    out = np.full(len(df), np.nan); n_prev = np.zeros(len(df))
    for _, idx in df.groupby(key).indices.items():
        idx = np.sort(idx); v = df[col].values[idx].astype(float); se = df.season.values[idx]
        for j in range(1, len(idx)):
            m = se[:j] >= se[j] - 1
            if not m.any():
                continue
            ages = (j - np.arange(j))[m]; w = 0.5 ** (ages / HP)
            out[idx[j]] = np.sum(w * v[:j][m]) / w.sum(); n_prev[idx[j]] = m.sum()
    return out, n_prev


def features(HP):
    p = os.path.join(CACHE, f'props_feat_HP{HP}.pkl')
    if os.path.exists(p):
        return pd.read_pickle(p)
    pg = player_games().copy()
    for c in ('passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'anytime_td', 'targets', 'carries'):
        pg[f'b_{c}'], pg['n_prev'] = ew_before(pg, 'player_id', c, HP)
    pg['l8_pass'] = pg.groupby('player_id').passing_yards.transform(lambda x: x.shift().rolling(8, 1).mean())
    for c in ('rushing_yards', 'receiving_yards', 'receptions'):
        pg[f'l8_{c}'] = pg.groupby('player_id')[c].transform(lambda x: x.shift().rolling(8, 1).mean())
    pg['l8_passing_yards'] = pg.pop('l8_pass')
    # opponent factor: stat allowed to the position group per game (team-game level), EW over the defense's earlier games
    grp = pg.assign(pgp=np.where(pg.position == 'FB', 'RB', pg.position))
    allowed = grp.groupby(['game_id', 'opponent_team', 'pgp', 'season', 'kick'])[['passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'anytime_td']].sum().reset_index()
    allowed = allowed.sort_values('kick').reset_index(drop=True)
    for c in ('passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'anytime_td'):
        allowed[f'a_{c}'], _ = ew_before(allowed.assign(k=allowed.opponent_team + '|' + allowed.pgp), 'k', c, HP)
        allowed[f'lg_{c}'] = allowed.groupby(['season', 'pgp'])[c].transform(lambda x: x.shift().expanding().mean())
        allowed[f'lg_{c}'] = allowed[f'lg_{c}'].fillna(allowed.groupby('pgp')[c].transform('mean'))
    grp = grp.merge(allowed[['game_id', 'opponent_team', 'pgp'] + [f'a_{c}' for c in STATS] + [f'lg_{c}' for c in STATS]],
                    on=['game_id', 'opponent_team', 'pgp'], how='left')
    # team totals from the closing line (home spread_line = home margin)
    sch = nfl.schedule()
    tt = pd.concat([sch.assign(team=sch.home_team, ttot=sch.total_line / 2 + sch.spread_line / 2),
                    sch.assign(team=sch.away_team, ttot=sch.total_line / 2 - sch.spread_line / 2)])[['game_id', 'team', 'ttot', 'season', 'wind_x', 'cold_x', 'wx_missing', 'dome']]
    lgtt = tt.groupby('season').ttot.mean().shift()          # previous season's average (no look-ahead)
    tt['tt'] = tt.ttot / tt.season.map(lgtt).fillna(tt.ttot.mean()) - 1
    grp = grp.merge(tt.drop(columns='season'), on=['game_id', 'team'], how='left')
    # injuries this week: player Questionable; key receivers / lead RB Out or Doubtful
    inj = data.nfl_injuries(range(2013, 2027)).dropna(subset=['full_name'])
    inj = inj.assign(k1=inj.full_name.map(lambda s: ' '.join(toks(s))))[['season', 'week', 'team', 'k1', 'report_status']].drop_duplicates(['season', 'week', 'team', 'k1'])
    grp = grp.merge(inj, on=['season', 'week', 'team', 'k1'], how='left')
    grp['quest'] = grp.report_status.eq('Questionable').astype(float)
    out_ = inj[inj.report_status.isin(['Out', 'Doubtful'])]
    # team's latest EW targets / carries per player, as of before this week (post-game state of earlier games)
    post = pg[['player_id', 'k1', 'team', 'season', 'week', 'kick', 'b_targets', 'b_carries', 'position']].copy()
    key_out, rb_out = [], []
    lastv = {}
    by_week = grp.groupby(['season', 'week'])
    state = post.sort_values('kick')
    st_iter = iter(state.itertuples(index=False)); pending = next(st_iter, None)
    for (y, wk), x in sorted(by_week, key=lambda kv: kv[0]):
        while pending is not None and (pending.season, pending.week) < (y, wk):
            if not np.isnan(pending.b_targets):
                lastv[(pending.team, pending.k1)] = (pending.b_targets, pending.b_carries if not np.isnan(pending.b_carries) else 0.0,
                                                     pending.position, pending.season)
            pending = next(st_iter, None)
        outs = out_[(out_.season == y) & (out_.week == wk)]
        for t, xt in x.groupby('team'):
            roster = {k: v for (tm, k), v in lastv.items() if tm == t and v[3] >= y - 1}
            top2 = sorted(roster, key=lambda k: -roster[k][0])[:2]
            rbs = [k for k in roster if roster[k][2] in ('RB', 'FB')]
            lead = max(rbs, key=lambda k: roster[k][1]) if rbs else None
            o = set(outs[outs.team == t].k1)
            for i, k in zip(xt.index, xt.k1):
                key_out.append((i, float(sum(1 for r in top2 if r != k and r in o))))
                rb_out.append((i, float(lead is not None and lead != k and lead in o)))
    grp['key_out'] = pd.Series(dict(key_out)); grp['rb_out'] = pd.Series(dict(rb_out))
    # backup QB for the team: first-dropback starter with < 4 earlier starts (from the game model's QB logic)
    X = nfl.extras()[['game_id', 'home_qb', 'away_qb']]
    pb = data.nfl_pbp(range(2006, 2027))
    db = pb[(pb.qb_dropback == 1) & pb.passer_player_id.notna()].sort_values(['game_id', 'play_id'])
    first = db.drop_duplicates(['game_id', 'posteam'])[['game_id', 'posteam', 'passer_player_id']]
    first = first.merge(sch[['game_id', 'gameday']], on='game_id').sort_values('gameday')
    first['starts_before'] = first.groupby('passer_player_id').cumcount()
    first['backup'] = (first.starts_before < 4).astype(float)
    grp = grp.merge(first.rename(columns={'posteam': 'team', 'passer_player_id': 'starter_id'})[['game_id', 'team', 'starter_id', 'backup']],
                    on=['game_id', 'team'], how='left')
    grp['backup'] = grp.backup.fillna(0.0)
    for c in ('wind_x', 'cold_x', 'wx_missing', 'dome', 'key_out', 'rb_out', 'tt'):
        grp[c] = grp[c].fillna(0.0)
    grp.to_pickle(p)
    return grp


def stat_rows(f, stat):
    pos = STATS[stat]
    x = f[f.position.isin(pos) | ((stat in ('rushing_yards', 'receiving_yards', 'receptions')) & f.position.eq('FB') & ('RB' in pos))]
    if stat == 'passing_yards':
        x = x[x.player_id == x.starter_id]
    x = x[(x.n_prev >= 3) & x[f'b_{stat}'].notna()].copy()
    x['base'] = x[f'b_{stat}']
    x['opp'] = (x[f'a_{stat}'] / x[f'lg_{stat}'] - 1).replace([np.inf, -np.inf], np.nan).fillna(0).clip(-0.8, 2)
    if stat != 'anytime_td':
        x['line'] = np.floor(x[f'l8_{stat}']) + 0.5
    else:
        x['line'] = 0.5
    if stat in LINE_FLOOR:
        x = x[x.line >= LINE_FLOOR[stat]]
    return x


def fit_stat(x, stat):
    e = x[x.season.between(*EARLY)]
    if stat == 'anytime_td':
        from sklearn.linear_model import LogisticRegression
        Xe = np.column_stack([np.log(e.base + 0.01)] + [e[a] for a in ADJ])
        m = LogisticRegression(C=1e6, max_iter=2000).fit(Xe, e[stat] > 0.5)
        return dict(kind='logit', model=m)
    A = e.base.values[:, None] * np.column_stack([np.ones(len(e))] + [e[a].values for a in ADJ])
    b, *_ = np.linalg.lstsq(A, e[stat].values, rcond=None)
    pred = np.maximum(A @ b, 0.05 * e.base.values)
    q = np.quantile(pred, [1 / 3, 2 / 3])
    tb = np.digitize(pred, q)
    ratios = {t: np.sort(e[stat].values[tb == t] / pred[tb == t]) for t in range(3)}
    return dict(kind='ratio', b=b, cuts=q, ratios=ratios)


def predict(x, F, stat):
    if F['kind'] == 'logit':
        X = np.column_stack([np.log(x.base + 0.01)] + [x[a] for a in ADJ])
        return F['model'].predict_proba(X)[:, 1], None
    A = x.base.values[:, None] * np.column_stack([np.ones(len(x))] + [x[a].values for a in ADJ])
    pred = np.maximum(A @ F['b'], 0.05 * x.base.values)
    tb = np.digitize(pred, F['cuts'])
    p = np.array([1 - np.searchsorted(F['ratios'][t], L / pr, side='right') / len(F['ratios'][t]) for t, L, pr in zip(tb, x.line.values, pred)])
    return p, pred


def evaluate(x, p, stat, naive):
    y = (x[stat].values > x.line.values).astype(float)
    out = {}
    for name, per in (('early', EARLY), ('late', LATE)):
        m = x.season.between(*per).values
        out[name] = dict(n=int(m.sum()), brier=float(np.mean((p[m] - y[m]) ** 2)), naive=float(np.mean((naive - y[m]) ** 2)),
                         over_rate=float(y[m].mean()), pred_mean=float(p[m].mean()))
    m = x.season.between(*LATE).values
    bins = np.clip((p[m] * 10).astype(int), 0, 9); gaps = []
    for b_ in range(10):
        s = bins == b_
        if s.sum() >= 100:
            gaps.append(abs(p[m][s].mean() - y[m][s].mean()))
    out['worst_gap_late'] = float(max(gaps)) if gaps else None
    out['calibrated'] = bool(gaps) and max(gaps) <= 0.05
    out['beats_naive'] = out['early']['brier'] < out['early']['naive'] and out['late']['brier'] < out['late']['naive']
    return out


def dk_check(F_all, HP):
    """v8/prices/dk_props.csv (Chris's DK prices, logged before kickoff): model chance vs DK break-even, Brier."""
    pth = os.path.join(ROOT, 'v8', 'prices', 'dk_props.csv')
    d = pd.read_csv(pth)
    d = d[d.result.notna() & (pd.to_datetime(d.logged_at, utc=True) < pd.to_datetime(d.kickoff, utc=True))]
    f = features(HP)
    rows = []
    for _, r in d.iterrows():
        st = r.stat
        if st not in STATS:
            continue
        x = stat_rows(f, st)
        k = ' '.join(toks(r.player))
        m = x[(x.k1 == k) & (x.season == 2026) & (pd.to_datetime(x.kick).dt.strftime('%Y-%m-%d') == pd.to_datetime(r.kickoff, utc=True).tz_convert('America/New_York').strftime('%Y-%m-%d'))]
        if m.empty:
            continue
        m = m.iloc[[0]].copy(); m['line'] = r.line
        p, _ = predict(m, F_all[st], st)
        be = lambda a: (-a / (-a + 100)) if a < 0 else (100 / (a + 100))
        po = be(float(r.over)) if pd.notna(r.over) else np.nan
        pu = be(float(r.under)) if pd.notna(r.under) else np.nan
        pdk = po / (po + pu) if pd.notna(pu) and pd.notna(po) else po
        if pd.isna(pdk):
            continue
        rows.append(dict(player=r.player, stat=st, line=r.line, model=float(p[0]), dk=float(pdk), y=float(float(r.result) > r.line)))
    z = pd.DataFrame(rows)
    return z


if __name__ == '__main__':
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    txt = ['core NFL props (core/PROTOCOL.md amendment 9). Test line = player\'s last-8 mean rounded to x.5 (TD 0.5).']
    ll = {}
    for HP in HP_GRID:
        f = features(HP); tot = 0.0
        for st in STATS:
            x = stat_rows(f, st); F = fit_stat(x, st); p, _ = predict(x, F, st)
            e = x.season.between(*EARLY).values; y = (x[st].values > x.line.values)[e]; pe = np.clip(p[e], 1e-4, 1 - 1e-4)
            tot += float(-np.mean(y * np.log(pe) + (1 - y) * np.log(1 - pe)))
        ll[HP] = tot; txt.append(f'HP={HP:2d}: EARLY log loss (sum over 5 stats) {tot:.4f}')
    HP = min(ll, key=ll.get); txt.append(f'Chosen on EARLY only: HP = {HP}\n')
    f = features(HP); R, Fs = {}, {}
    for st in STATS:
        x = stat_rows(f, st); F = fit_stat(x, st); Fs[st] = F; p, _ = predict(x, F, st)
        naive = float((x[st] > x.line)[x.season.between(*EARLY)].mean())
        R[st] = evaluate(x, p, st, naive)
        r = R[st]
        txt.append(f"{st:16s} EARLY n={r['early']['n']:6d} Brier {r['early']['brier']:.4f} vs naive {r['early']['naive']:.4f} | "
                   f"LATE n={r['late']['n']:6d} Brier {r['late']['brier']:.4f} vs naive {r['late']['naive']:.4f} | worst calib gap LATE "
                   f"{(r['worst_gap_late'] or 0) * 100:.1f} pts | {'calibrated' if r['calibrated'] else 'NOT calibrated'}, "
                   f"{'beats naive' if r['beats_naive'] else 'does NOT beat naive'} | LATE Over rate {r['late']['over_rate']:.1%} vs predicted {r['late']['pred_mean']:.1%}")
        if F['kind'] == 'ratio':
            txt.append('    weights x base: ' + ', '.join(f'{n} {v:+.3f}' for n, v in zip(['const'] + ADJ, F['b'])))
    z = dk_check(Fs, HP)
    if len(z):
        bm = float(np.mean((z.model - z.y) ** 2)); bd = float(np.mean((z.dk - z.y) ** 2))
        txt.append(f"\nDK check (Chris's DK prices, Nov 25-27 2026, logged before kickoff): {len(z)} props matched | Brier model {bm:.4f} vs DK {bd:.4f} | "
                   f"Over hit {z.y.mean():.1%}, model said {z.model.mean():.1%}, DK said {z.dk.mean():.1%} - NOT a pass/fail (too few)")
        R['dk_check'] = dict(n=len(z), brier_model=bm, brier_dk=bd)
    open(os.path.join(HERE, 'results', 'props_nfl_floor.txt'), 'w').write('\n'.join(txt) + '\n')
    json.dump(dict(HP=HP, logloss=ll, results=R), open(os.path.join(HERE, 'results', 'props_nfl_floor.json'), 'w'), indent=1, default=float)
    print('\n'.join(txt))
