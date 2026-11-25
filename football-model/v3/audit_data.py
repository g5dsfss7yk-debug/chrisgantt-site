"""Rule 7: audit the input data before modeling. Prints missing values by season, sign checks, stale fields.
Run: python v3/audit_data.py > v3/results/data_audit.txt"""
import numpy as np, pandas as pd
import data

pd.set_option('display.width', 200)


def nfl():
    g = data.nfl_games()
    g = g[g.season >= 2002]
    print('=== NFL schedule (nflverse games.csv): share MISSING by season (completed games only)')
    done = g[g.result.notna()]
    cols = ['spread_line', 'total_line', 'home_spread_odds', 'over_odds', 'home_moneyline', 'temp', 'wind',
            'roof', 'surface', 'home_qb_name', 'referee']
    m = done.groupby('season')[cols].apply(lambda d: d.isna().mean().round(2))
    m['games'] = done.groupby('season').size()
    print(m.to_string())
    out = done[~done.roof.isin(['dome', 'closed'])]
    print('\nWind missing in OUTDOOR games by 2026 week:')
    print(out[out.season == 2026].groupby('week').wind.apply(lambda s: s.isna().mean()).round(2).to_dict())
    # sign: spread_line > 0 should mean home favored -> home moneyline negative
    s = done.dropna(subset=['spread_line', 'home_moneyline'])
    s = s[s.spread_line.abs() >= 3]
    agree = ((s.spread_line > 0) == (s.home_moneyline < 0)).mean()
    print(f'\nSign check: spread_line>0 <=> home ML favorite in {agree:.1%} of {len(s)} games (|line|>=3)')
    print(f'Result check: result == home_score - away_score in {(done.result == done.home_score - done.away_score).mean():.1%}')
    print(f'Total check: total == home+away in {(done.total == done.home_score + done.away_score).mean():.1%}')
    # stale QB: listed QB vs QB with most dropbacks in pbp
    pb = data.nfl_pbp(range(2016, 2027))
    qb = (pb[pb.qb_dropback == 1].groupby(['game_id', 'posteam', 'passer_player_id']).size()
          .reset_index(name='n').sort_values('n').drop_duplicates(['game_id', 'posteam'], keep='last'))
    qb = qb.set_index(['game_id', 'posteam']).passer_player_id
    rows = []
    for _, r in done[done.season >= 2016].iterrows():
        for side in ('home', 'away'):
            k = (r.game_id, r[f'{side}_team'])
            if k in qb.index and isinstance(r[f'{side}_qb_id'], str):
                rows.append((r.season, r[f'{side}_qb_id'] == qb[k]))
    q = pd.DataFrame(rows, columns=['season', 'same'])
    print('\nListed QB (games.csv) == QB with most dropbacks (pbp), by season:')
    print(q.groupby('season').same.mean().round(3).to_dict())
    print('\nPBP coverage: games in pbp / completed games, and EPA missing on pass+run plays:')
    cov = pb.groupby('season').game_id.nunique() / done[done.season >= 2016].groupby('season').size()
    pr = pb[(pb['pass'] == 1) | (pb['rush'] == 1)]
    print(pd.DataFrame({'coverage': cov.round(3), 'epa_missing': pr.groupby('season').epa.apply(lambda s: s.isna().mean()).round(4)}).to_string())


def cfb():
    print('\n=== CFB (CollegeFootballData lines). spread = HOME number (-7 = home favored)')
    rows = []
    for y in range(2014, 2027):
        L = data.cfb_lines(y)
        L = L[L.home_score.notna()]
        for p, d in L.groupby('provider'):
            ml = d.dropna(subset=['spread', 'home_ml', 'away_ml'])
            ml = ml[ml.spread.abs() >= 3]
            sign = ((ml.spread < 0) == (ml.home_ml < ml.away_ml)).mean() if len(ml) else np.nan
            rows.append({'season': y, 'provider': p, 'games': d.id.nunique(), 'spread_missing': d.spread.isna().mean(),
                         'total_missing': d.total.isna().mean(), 'ml_sign_ok': sign})
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    # DK vs other books on the same game: how different?
    for y in (2023, 2024, 2025, 2026):
        L = data.cfb_lines(y).dropna(subset=['spread'])
        p = L.pivot_table(index='id', columns='provider', values='spread', aggfunc='first')
        if 'DraftKings' not in p: continue
        oth = p.drop(columns='DraftKings').median(axis=1)
        d = (p.DraftKings - oth).dropna()
        print(f'{y}: DK spread minus median other book: n={len(d)}, |diff|>=1 in {(d.abs() >= 1).mean():.1%}, '
              f'|diff|>=5 (likely sign/stale error) {(d.abs() >= 5).sum()} games')
    a = data.cfb_adv(2025)
    print('\nAdvanced stats 2025: rows', len(a), 'missing ppa', a.o_ppa.isna().mean())


if __name__ == '__main__':
    nfl(); cfb()
