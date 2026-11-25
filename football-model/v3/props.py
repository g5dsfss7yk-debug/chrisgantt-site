"""v3 NFL player props (see v3/PROTOCOL.md "Props").

Projection = player's weighted per-game average (half-life 6 games, prior games only)
             x opponent factor (defense's weighted allowed per game to that position / league average).
Chance over a line = share of TRAINING player-games (2013-2022) with a similar projection whose
actual/projection ratio cleared line/projection. Anytime TD = TD rate of training player-games with a
similar projected TD count. Prices both the Over and the Under.
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'v3')
HL = 6.0
TRAIN = (2013, 2022)
STATS = {  # stat: (positions, row filter)
    'passing_yards': (['QB'], lambda d: d.attempts >= 10),
    'rushing_yards': (['RB', 'QB'], lambda d: d.carries >= 1),
    'receiving_yards': (['WR', 'TE', 'RB'], lambda d: d.targets >= 1),
    'receptions': (['WR', 'TE', 'RB'], lambda d: d.targets >= 1),
    'anytime_td': (['RB', 'WR', 'TE'], lambda d: (d.carries + d.targets) >= 1),
}


def weekly(seasons=range(2012, 2027)):
    d = pd.concat([pd.read_parquet(os.path.join(ROOT, 'stats', f'w_{y}.parquet')) for y in seasons], ignore_index=True)
    d['anytime_td'] = ((d.rushing_tds.fillna(0) + d.receiving_tds.fillna(0)) >= 1).astype(float)
    d['td_count'] = d.rushing_tds.fillna(0) + d.receiving_tds.fillna(0)
    d['order'] = d.season * 100 + np.where(d.season_type == 'REG', 0, 30) + d.week
    return d.sort_values(['order']).reset_index(drop=True)


def _ew_prior(values, groups):
    """Exponentially weighted mean of prior rows within each group (half-life HL rows)."""
    out = np.full(len(values), np.nan)
    a = 0.5 ** (1 / HL)
    df = pd.DataFrame({'v': values, 'g': groups})
    for _, idx in df.groupby('g').indices.items():
        num = den = 0.0
        for i in idx:
            if den > 0:
                out[i] = num / den
            v = values[i]
            if not np.isnan(v):
                num, den = num * a + v, den * a + 1
            else:
                num, den = num * a, den * a
    return out


def project(d, stat):
    """Adds proj_<stat> (needs >= 3 prior qualifying games) using only earlier rows."""
    pos, filt = STATS[stat]
    s = d[d.position.isin(pos)].copy()
    s = s[filt(s)].copy()
    src = 'td_count' if stat == 'anytime_td' else stat
    s['_v'] = s[src].astype(float)
    s['_n'] = s.groupby('player_id').cumcount()
    s['p_avg'] = _ew_prior(s._v.values, s.player_id.values)
    # opponent factor: what this defense allowed per game to the position, vs the league
    dg = s.groupby(['opponent_team', 'order', 'position'])._v.sum().reset_index()
    dg['key'] = dg.opponent_team + '|' + dg.position
    dg['allowed'] = _ew_prior(dg._v.values, dg.key.values)
    lg = dg.groupby(['order', 'position']).allowed.mean().rename('lg').reset_index()
    dg = dg.merge(lg, on=['order', 'position'])
    dg['opp_f'] = dg.allowed / dg.lg
    s = s.merge(dg[['opponent_team', 'order', 'position', 'opp_f']], on=['opponent_team', 'order', 'position'], how='left')
    s['proj'] = s.p_avg * s.opp_f.fillna(1.0)
    s.loc[s._n < 3, 'proj'] = np.nan
    return s


class Pricer:
    """Empirical over-chance tables from the training seasons."""

    def __init__(self, s, stat, train=TRAIN):
        self.stat = stat
        t = s[(s.season >= train[0]) & (s.season <= train[1]) & s.proj.notna() & (s.proj > 0)]
        self.edges = {}
        self.tab = {}
        for pos, tp in t.groupby('position'):
            e = np.unique(np.quantile(tp.proj, np.linspace(0, 1, 11)))
            e[0], e[-1] = -np.inf, np.inf
            b = np.digitize(tp.proj, e[1:-1])
            self.edges[pos] = e
            if stat == 'anytime_td':
                self.tab[pos] = tp.groupby(b)._v.apply(lambda v: (v >= 1).mean()).to_dict()
            else:
                self.tab[pos] = {k: np.sort((tp._v / tp.proj).values[b == k]) for k in np.unique(b)}

    def p_over(self, pos, proj, line=None):
        if pos not in self.edges or not (proj > 0):
            return np.nan
        k = int(np.digitize([proj], self.edges[pos][1:-1])[0])
        if self.stat == 'anytime_td':
            return self.tab[pos].get(k, np.nan)
        r = self.tab[pos][k]
        return 1 - np.searchsorted(r, line / proj, side='right') / len(r)


def fair_american(p):
    if not (0 < p < 1):
        return None
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def half(x):
    return np.floor(x) + 0.5


def calibration_test():
    d = weekly()
    out = {}
    lines_txt = []
    for stat in STATS:
        s = project(d, stat)
        pr = Pricer(s, stat)
        ev = s[(s.season >= 2023) & s.proj.notna() & (s.proj > 0)]
        P, Y = [], []
        for _, r in ev.iterrows():
            if stat == 'anytime_td':
                P.append(pr.p_over(r.position, r.proj)); Y.append(r._v >= 1)
                continue
            mults = (0.6, 1.0, 1.4) if stat != 'receptions' else (None,)
            ls = [half(r.proj * m) for m in mults] if stat != 'receptions' else [half(r.proj) - 1, half(r.proj), half(r.proj) + 1]
            for L in ls:
                if L < 0.5:
                    continue
                P.append(pr.p_over(r.position, r.proj, L)); Y.append(r._v > L)
        P, Y = np.array(P, float), np.array(Y, float)
        ok = ~np.isnan(P)
        P, Y = P[ok], Y[ok]
        dec = np.minimum((P * 10).astype(int), 9)
        tab = pd.DataFrame({'d': dec, 'p': P, 'y': Y}).groupby('d').agg(pred=('p', 'mean'), hit=('y', 'mean'), n=('y', 'size'))
        tab = tab[tab.n >= 50]
        worst = float((tab.hit - tab.pred).abs().max())
        passed = worst <= 0.03
        out[stat] = {'n': int(len(P)), 'worst_gap': worst, 'pass': passed, 'table': tab.round(3).to_dict('index')}
        lines_txt.append(f"{stat:16s} {len(P):7d} line checks 2023-26, worst decile gap {worst:.1%} -> "
                         f"{'CALIBRATED' if passed else 'NOT calibrated'}")
        lines_txt.append('   ' + '  '.join(f"{int(k)*10}-{int(k)*10+10}%: pred {v.pred:.0%} hit {v.hit:.0%}" for k, v in tab.iterrows()))
    return out, '\n'.join(lines_txt)


if __name__ == '__main__':
    import json
    res, txt = calibration_test()
    print(txt)
    RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
    json.dump(res, open(os.path.join(RES, 'props_results.json'), 'w'), indent=1, default=float)
    open(os.path.join(RES, 'props_results.txt'), 'w').write(
        'Props calibration (train 2013-22, test 2023-26; lines at 0.6x/1.0x/1.4x projection, receptions proj-1/proj/proj+1)\n'
        'Beating DK prices: NOT tested (no DK price history). Every prop is a LEAN.\n' + txt + '\n')
