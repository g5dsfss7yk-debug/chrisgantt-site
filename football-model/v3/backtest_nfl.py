"""NFL v3 backtest, run in two stages exactly as v3/PROTOCOL.md says.
  python v3/backtest_nfl.py early   -> settings grid on 2006-2016 ONLY, writes results/nfl_settings.json
  python v3/backtest_nfl.py late    -> every bet type, EARLY and LATE, with pass/fail (run once)"""
import json, os, sys
import numpy as np, pandas as pd
import nfl, grade

EARLY, LATE = (2006, 2016), (2017, 2026)
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')


def spread_bets(f, thr):
    f = f[f.pm.notna() & f.result.notna()]
    edge = f.pm - f.spread_line
    f = f[edge.abs() >= thr]
    edge = edge[edge.abs() >= thr]
    home = edge > 0
    cover = np.where(home, f.result > f.spread_line, f.result < f.spread_line)
    push = f.result == f.spread_line
    price = np.full(len(f), -110.0)  # DK standard (PROTOCOL amendment 1)
    return cover, push, price, f


def total_bets(f, thr):
    f = f[f.pt.notna() & f.total.notna()]
    edge = f.pt - f.total_line
    f, edge = f[edge.abs() >= thr], edge[edge.abs() >= thr]
    over = edge > 0
    win = np.where(over, f.total > f.total_line, f.total < f.total_line)
    push = f.total == f.total_line
    price = np.full(len(f), -110.0)  # DK standard (PROTOCOL amendment 1)
    return win, push, price, f


def ml_bets(f):
    from math import erf, sqrt
    f = f[f.pm.notna() & f.result.notna() & f.home_moneyline.notna() & f.away_moneyline.notna()]
    ph = 0.5 * (1 + np.vectorize(erf)((f.pm.values) / (f.sd.values * sqrt(2))))
    dh, da = grade.dec(f.home_moneyline), grade.dec(f.away_moneyline)
    evh, eva = ph * dh - 1, (1 - ph) * da - 1
    take_h, take_a = evh >= 0.03, eva >= 0.03
    win = np.concatenate([(f.result > 0).values[take_h], (f.result < 0).values[take_a]])
    push = np.concatenate([(f.result == 0).values[take_h], (f.result == 0).values[take_a]])
    price = np.concatenate([f.home_moneyline.values[take_h], f.away_moneyline.values[take_a]])
    return win, push, price


def teaser_legs(f, lo, hi, side, max_total=None):
    """6-pt teaser legs; side='dog' takes dogs getting lo..hi, 'fav' takes favorites laying lo..hi. Push = loss."""
    f = f[f.result.notna()]
    if max_total is not None:
        f = f[f.total_line <= max_total]
    L = f.spread_line  # >0 home favored
    rows = []
    hd = (L <= -lo) & (L >= -hi) if side == 'dog' else (L >= lo) & (L <= hi)    # home is the dog / fav
    ad = (L >= lo) & (L <= hi) if side == 'dog' else (L <= -lo) & (L >= -hi)    # away is the dog / fav
    # home leg: home margin + (home's line) + 6 > 0 ; home's line = -L
    hw = (f.result - L + 6) > 0
    aw = (-f.result + L + 6) > 0
    return np.concatenate([hw[hd].values, aw[ad].values]), np.concatenate([f.season[hd].values, f.season[ad].values])


def qb_change_under(f, tg):
    t = tg.merge(f[['game_id', 'gameday', 'season']], on='game_id').sort_values(['team', 'gameday'])
    t['prev_qb'] = t.groupby(['team', 'season']).qb.shift()
    ch = t[t.prev_qb.notna() & t.qb.notna() & (t.qb != t.prev_qb)][['game_id', 'team']]
    g = f.merge(ch.rename(columns={'team': 'home_team'}), on=['game_id', 'home_team'])
    g = g[g.total.notna()]
    return (g.total < g.total_line).values, (g.total == g.total_line).values, np.full(len(g), -110.0), g


def period(df, p):
    return (df.season >= p[0]) & (df.season <= p[1])


def stage_early():
    rows = []
    for H in (4, 8, 16):
        for G in (0, 8):
            f, _, _ = nfl.build(H, G)
            f = nfl.walk_forward(f, EARLY[0], EARLY[1])
            e = f[period(f, EARLY)]
            c, p, pr, _ = spread_bets(e, 0)
            r = grade.record(c, pr, p)
            rows.append({'H': H, 'G': G, **r})
            print(f'H={H:2d} G={G}: EARLY spread all games {grade.fmt(r)}', flush=True)
    best = max(rows, key=lambda r: (round(r['pct'], 4), r['H'], -r['G']))
    json.dump({'H': best['H'], 'G': best['G'], 'grid': rows}, open(os.path.join(RES, 'nfl_settings.json'), 'w'), indent=1)
    print('chosen:', best['H'], best['G'])


def stage_late():
    s = json.load(open(os.path.join(RES, 'nfl_settings.json')))
    f, tg, _ = nfl.build(s['H'], s['G'])
    f = nfl.walk_forward(f, EARLY[0], LATE[1])
    f.to_pickle(os.path.join(RES, 'nfl_backtest.pkl'))
    out, lines = {}, []
    def add(name, fn, kind='rate', recent=True):
        e, l = fn(f[period(f, EARLY)]), fn(f[period(f, LATE)])
        r23 = fn(f[period(f, (2023, 2026))]) if recent else None
        ok = grade.passes(e, l, kind)
        out[name] = {'early': e, 'late': l, 'recent_2023_26': r23, 'pass': ok}
        lines.append(f"{name:38s} EARLY {grade.fmt(e):42s} LATE {grade.fmt(l):42s} "
                     f"{'2023-26 ' + grade.fmt(r23) if r23 else ''}  -> {'TESTED PICK' if ok else 'LEAN'}")
    for t in (0, 1, 2):
        add(f'spread edge {t}+', lambda d, t=t: (lambda c, p, pr, _: grade.record(c, pr, p))(*spread_bets(d, t)))
    for t in (0, 1, 2):
        add(f'total edge {t}+', lambda d, t=t: (lambda c, p, pr, _: grade.record(c, pr, p))(*total_bets(d, t)))
    add('moneyline EV 3%+', lambda d: (lambda w, p, pr: grade.record(w, pr, p))(*ml_bets(d)), kind='roi')
    def leg(d, lo, hi, side, mt=None):
        w, _ = teaser_legs(d, lo, hi, side, mt)
        r = grade.record(w)
        r['be'] = 0.739   # 2-team 6-pt teaser at -120: sqrt(1/1.8333)
        r['roi'] = np.nan
        return r
    add('teaser leg dog +1.5..+2.5', lambda d: leg(d, 1.5, 2.5, 'dog'))
    add('teaser leg fav -7.5..-8.5', lambda d: leg(d, 7.5, 8.5, 'fav'))
    add('teaser leg dog +1.5..+2.5, total<=44*', lambda d: leg(d, 1.5, 2.5, 'dog', 44))
    add('home QB change -> Under*', lambda d: (lambda w, p, pr, _: grade.record(w, pr, p))(*qb_change_under(d, tg)))
    # model lean records by side type (information only)
    txt = '\n'.join(lines)
    print(txt)
    json.dump({'settings': s, 'results': out}, open(os.path.join(RES, 'nfl_results.json'), 'w'), indent=1, default=float)
    with open(os.path.join(RES, 'nfl_results.txt'), 'w') as fh:
        fh.write(f"NFL v3 backtest (settings H={s['H']} G={s['G']}, chosen on EARLY). * = found by an earlier search\n{txt}\n")


if __name__ == '__main__':
    {'early': stage_early, 'late': stage_late}[sys.argv[1]]()
