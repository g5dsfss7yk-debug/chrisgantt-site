"""NFL player value out (core/PROTOCOL.md amendment 13). python core/players_nfl.py -> core/results/players_nfl.txt"""
import os, sys, json, math
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data, nfl, cfb

HV = 8
OL = {'T', 'G', 'C', 'LT', 'LG', 'RG', 'RT', 'OL'}
NEW = ['off_val_out', 'def_val_out', 'off_val_q', 'def_val_q', 'ol_out']
CACHE = os.path.join(data.DATA, 'nfl', 'player_values.pkl')


def values():
    w = data.nfl_weekly(range(2012, 2027))
    w = w[w.season_type == 'REG'].copy()
    g = nfl.schedule()[['game_id', 'gameday']]
    w = w.merge(g, on='game_id', how='left').sort_values(['gameday', 'game_id'])
    off = w.position_group.isin(['RB', 'WR', 'TE'])
    dfn = w.position_group.isin(['DL', 'LB', 'DB'])
    w['v'] = np.where(off, w.receiving_epa.fillna(0) + w.rushing_epa.fillna(0),
                      np.where(dfn, w.def_sacks.fillna(0) + 0.5 * w.def_qb_hits.fillna(0) + w.def_interceptions.fillna(0)
                               + 0.5 * w.def_pass_defended.fillna(0) + 0.5 * w.def_tackles_for_loss.fillna(0) + w.def_fumbles_forced.fillna(0), np.nan))
    w['side'] = np.where(off, 'O', np.where(dfn, 'D', None))
    w = w[w.side.notna()].reset_index(drop=True)
    # value AFTER each game (EW over that game and earlier ones, last two seasons) -> used for the player's NEXT games
    post = np.full(len(w), np.nan)
    for _, idx in w.groupby('player_id').indices.items():
        idx = np.sort(idx); v = w.v.values[idx]; se = w.season.values[idx]
        for j in range(len(idx)):
            m = se[:j + 1] >= se[j] - 1; ages = (j - np.arange(j + 1))[m]; ww = 0.5 ** (ages / HV)
            post[idx[j]] = np.sum(ww * v[:j + 1][m]) / ww.sum()
    w['val_after'] = post
    return w[['player_id', 'season', 'week', 'gameday', 'team', 'side', 'val_after']]


def team_game_vars():
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    V = values()
    inj = data.nfl_injuries(range(2012, 2027))[['season', 'week', 'team', 'gsis_id', 'report_status', 'game_type']]
    inj = inj[(inj.game_type == 'REG') & inj.report_status.isin(['Out', 'Doubtful', 'Questionable'])].dropna(subset=['gsis_id'])
    sch = nfl.schedule()
    sch = sch[(sch.season >= 2012) & (sch.game_type == 'REG')]
    rows = []
    Vs = V.sort_values('gameday')
    for (y, wk), ij in inj.groupby(['season', 'week']):
        day = sch[(sch.season == y) & (sch.week == wk)].gameday.min()
        if pd.isna(day):
            continue
        last = Vs[(Vs.gameday < day) & (Vs.season >= y - 1)].drop_duplicates('player_id', keep='last').set_index('player_id')
        m = ij.join(last[['side', 'val_after']], on='gsis_id').dropna(subset=['val_after'])
        m['out'] = m.report_status.isin(['Out', 'Doubtful'])
        for t, x in m.groupby('team'):
            rows.append(dict(season=y, week=wk, team=t,
                             off_val_out=x[(x.side == 'O') & x.out].val_after.sum(), def_val_out=x[(x.side == 'D') & x.out].val_after.sum(),
                             off_val_q=x[(x.side == 'O') & ~x.out].val_after.sum(), def_val_q=x[(x.side == 'D') & ~x.out].val_after.sum()))
    tv = pd.DataFrame(rows)
    # OL starters out (previous week's depth chart), same matching as the game model's starters
    S = nfl._starters(); S = S[S.pos.isin(OL)]
    ol = []
    injo = inj[inj.report_status.isin(['Out', 'Doubtful'])]
    g2 = sch.assign(kick=pd.to_datetime(sch.gameday + ' ' + sch.gametime.fillna('13:00'), errors='coerce'))
    for _, r in pd.concat([g2.assign(team=g2.home_team), g2.assign(team=g2.away_team)]).iterrows():
        y, t, wk = r.season, r.team, r.week
        if y <= 2024:
            o = S[(S.season == y) & (S.team == t) & S.dt.isna()]
            prev = sorted(w_ for w_ in o.week.dropna().unique() if w_ < wk) or sorted(w_ for w_ in o.week.dropna().unique() if w_ == wk)
            if not prev:
                continue
            st = o[o.week == prev[-1]]
        else:
            k = pd.Timestamp(r.kick).tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC') if pd.notna(r.kick) else None
            nn = S[(S.season == y) & (S.team == t) & S.dt.notna()]
            nn = nn[nn.dt <= k - pd.Timedelta(days=6)] if k is not None else nn.iloc[:0]
            if nn.empty:
                continue
            st = nn[nn.dt == nn.dt.max()]
        ids = set(st.gsis_id)
        ol.append(dict(season=y, week=wk, team=t, ol_out=float(injo[(injo.season == y) & (injo.week == wk) & (injo.team == t)].gsis_id.isin(ids).sum())))
    tv = tv.merge(pd.DataFrame(ol), on=['season', 'week', 'team'], how='outer').fillna(0.0)
    out = []
    for _, r in sch.iterrows():
        h = tv[(tv.season == r.season) & (tv.week == r.week) & (tv.team == r.home_team)]
        a = tv[(tv.season == r.season) & (tv.week == r.week) & (tv.team == r.away_team)]
        hv = {c: float(h[c].iloc[0]) if len(h) else 0.0 for c in NEW}; av = {c: float(a[c].iloc[0]) if len(a) else 0.0 for c in NEW}
        d = dict(game_id=r.game_id)
        for c in NEW:
            d[f'm_{c}'] = hv[c] - av[c]; d[f't_{c}'] = hv[c] + av[c]
        out.append(d)
    out = pd.DataFrame(out); out.to_pickle(CACHE)
    return out


if __name__ == '__main__':
    X = team_game_vars()
    H = json.load(open(os.path.join(HERE, 'results', 'nfl_test.json')))['H']
    base = nfl.build(H).merge(X, on='game_id', how='left')
    for c in NEW:
        base[f'm_{c}'] = base[f'm_{c}'].fillna(0.0); base[f't_{c}'] = base[f't_{c}'].fillna(0.0)
    nfl.FIRST_FIT, nfl.EARLY = 2013, (2014, 2017)
    E, L = nfl.EARLY, nfl.LATE
    txt = [f'NFL player value out (amendment 13). Fit from 2013; EARLY 2014-17, LATE 2018-26; H = {H}.']
    res = {}
    old_extra = list(nfl.EXTRA)
    for lf in (False, True):
        nfl.LINE_FREE = lf
        for label, extra in (('WITHOUT player values', old_extra), ('WITH player values', old_extra + NEW)):
            nfl.EXTRA[:] = extra
            f = nfl.walk_forward(base)
            e = f[f.season.between(*E) & f.result.notna() & f.pm.notna()]
            txt.append(f"\n{'NO LINE' if lf else 'with the line'} - {label}: EARLY squared error margin {((e.pm - e.result) ** 2).mean():.1f}, total {((e.pt - e.total) ** 2).mean():.1f}")
            for kind in ('spread', 'total'):
                for t in (0, 2, 4, 7):
                    a, b = nfl.bets(f, E, kind, t)[:2], nfl.bets(f, L, kind, t)[:2]
                    p = cfb.pval(a[0] + b[0], a[1] + b[1])
                    ok = a[1] >= 100 and b[1] >= 100 and a[0] / max(a[1], 1) >= .524 and b[0] / max(b[1], 1) >= .524 and p < .05
                    txt.append(f"  {kind:6s} edge {t}+  EARLY {a[0]}/{a[1]} = {a[0] / max(a[1], 1):.1%} | LATE {b[0]}/{b[1]} = {b[0] / max(b[1], 1):.1%} | p={p:.3f} | {'TESTED PICK' if ok else 'LEAN'}")
                    res[f"{'noline' if lf else 'line'}|{label}|{kind}|{t}"] = dict(early=a, late=b, p=p, passes=ok)
            we, wl = nfl.winner_bets(f, E), nfl.winner_bets(f, L)
            txt.append(f"  winner 3%+   EARLY ROI {we[2].mean():+.1%} ({we[1]}) | LATE ROI {wl[2].mean():+.1%} ({wl[1]})")
            if label.startswith('WITH') and not lf:
                bm, _ = nfl.fit(f[f.season.between(2013, 2025)], 'margin')
                txt.append('  margin weights for the new variables: ' + ', '.join(f'{c} {bm[f"m_{c}"]:+.3f}' for c in NEW))
    nfl.LINE_FREE = False; nfl.EXTRA[:] = old_extra
    open(os.path.join(HERE, 'results', 'players_nfl.txt'), 'w').write('\n'.join(txt) + '\n')
    json.dump(res, open(os.path.join(HERE, 'results', 'players_nfl.json'), 'w'), indent=1, default=float)
    print('\n'.join(txt))
