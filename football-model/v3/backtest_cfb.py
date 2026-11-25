"""CFB v3 backtest in two stages (v3/PROTOCOL.md).
  python v3/backtest_cfb.py early  -> settings grid on 2014-2022 ONLY
  python v3/backtest_cfb.py late   -> every bet type, EARLY and LATE (run once)"""
import json, os, sys
import numpy as np, pandas as pd
import cfb, grade

EARLY, LATE = (2014, 2022), (2023, 2026)
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
SEASONS = list(range(cfb.FIRST, 2027))


def graded(f, p):
    """Rows of period p with the line they are graded against."""
    f = f[(f.season >= p[0]) & (f.season <= p[1]) & f.margin.notna()].copy()
    if p == LATE:
        f = f[f.dk_spread.notna()]
        f['g_spread'], f['g_total'] = f.dk_spread, f.dk_total
    else:
        f['g_spread'], f['g_total'] = f.med_spread, f.med_total
    return f


def spread_rec(f, thr):
    f = f[f.pm.notna() & f.g_spread.notna()]
    edge = f.pm + f.g_spread          # pred home margin - (-spread)
    f, edge = f[edge.abs() >= thr], edge[edge.abs() >= thr]
    ats = f.margin + f.g_spread
    win = np.where(edge > 0, ats > 0, ats < 0)
    return grade.record(win, None, ats == 0)


def total_rec(f, thr):
    f = f[f.pt.notna() & f.g_total.notna()]
    edge = f.pt - f.g_total
    f, edge = f[edge.abs() >= thr], edge[edge.abs() >= thr]
    win = np.where(edge > 0, f.tot > f.g_total, f.tot < f.g_total)
    return grade.record(win, None, f.tot == f.g_total)


def dk_gap_rec(f):
    f = f[f.dk_spread.notna() & f.oth_spread.notna()]
    d = f.dk_spread - f.oth_spread
    f, d = f[d.abs() >= 1], d[d.abs() >= 1]
    ats = f.margin + f.dk_spread
    win = np.where(d > 0, ats > 0, ats < 0)   # d>0: DK gives the home team more points -> home
    return grade.record(win, None, ats == 0)


def stage_early():
    g, a = cfb.load(SEASONS)
    rows = []
    for H in (3, 6, 12):
        for G in (0, 8):
            f = cfb.features(g, a, H, G, range(2013, EARLY[1] + 1))
            f = cfb.walk_forward(f, EARLY[0], EARLY[1])
            r = spread_rec(graded(f, EARLY), 0)
            rows.append({'H': H, 'G': G, **r})
            print(f'H={H:2d} G={G}: EARLY spread all games {grade.fmt(r)}', flush=True)
    best = max(rows, key=lambda r: (round(r['pct'], 4), r['H'], -r['G']))
    json.dump({'H': best['H'], 'G': best['G'], 'grid': rows}, open(os.path.join(RES, 'cfb_settings.json'), 'w'), indent=1)
    print('chosen:', best['H'], best['G'])


def stage_late():
    s = json.load(open(os.path.join(RES, 'cfb_settings.json')))
    g, a = cfb.load(SEASONS)
    f = cfb.features(g, a, s['H'], s['G'], range(2013, LATE[1] + 1))
    f = cfb.walk_forward(f, EARLY[0], LATE[1])
    f.to_pickle(os.path.join(RES, 'cfb_backtest.pkl'))
    E, L = graded(f, EARLY), graded(f, LATE)
    out, lines = {}, []
    def add(name, fn, both=True):
        e, l = (fn(E) if both else {'w': 0, 'n': 0, 'pct': np.nan, 'be': 0.524, 'roi': np.nan}), fn(L)
        ok = grade.passes(e, l)
        out[name] = {'early': e, 'late': l, 'pass': ok}
        lines.append(f"{name:28s} EARLY {grade.fmt(e):42s} LATE(DK line) {grade.fmt(l):42s} -> {'TESTED PICK' if ok else 'LEAN'}")
    for t in (0, 2, 4):
        add(f'spread edge {t}+', lambda d, t=t: spread_rec(d, t))
    for t in (0, 2, 4):
        add(f'total edge {t}+', lambda d, t=t: total_rec(d, t))
    add('DK gap 1+ vs other books', dk_gap_rec, both=False)
    txt = '\n'.join(lines)
    print(txt)
    json.dump({'settings': s, 'results': out}, open(os.path.join(RES, 'cfb_results.json'), 'w'), indent=1, default=float)
    with open(os.path.join(RES, 'cfb_results.txt'), 'w') as fh:
        fh.write(f"CFB v3 backtest (settings H={s['H']} G={s['G']}, chosen on EARLY)\n{txt}\n")


if __name__ == '__main__':
    {'early': stage_early, 'late': stage_late}[sys.argv[1]]()
