"""Different angles (core/PROTOCOL.md amendment 18): 1a era fit, 1b in-season recalibration, 2 direct classifier.
python core/approaches.py -> core/results/approaches.txt"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb, nfl

txt, res = ['Different angles (amendment 18). Same games as the current card models.'], {}


def college_frame():
    f = cfb.build(4).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    return f


def base_preds(mod, f, margin_window, total_window, total_mode, era_start=None):
    """Current card model (or era fit): walk-forward predictions pm, pt."""
    f = f.copy(); f['pm'] = np.nan; f['pt'] = np.nan; f['sd'] = np.nan
    first = cfb.FIRST if mod is cfb else nfl.FIRST_FIT
    for S in range(first + 1, 2027):
        def window(w):
            if era_start is not None and S > era_start:
                return era_start, S - 1                      # 1a: same era only
            return (first if w is None else max(first, S - w)), S - 1
        te = f.season == S
        a, b = window(margin_window); mod.TOTAL_MODE = 'ols'
        bm, sd = mod.fit(f[f.season.between(a, b)], 'margin')
        a, b = window(total_window); mod.TOTAL_MODE = total_mode
        bt, _ = mod.fit(f[f.season.between(a, b)], 'total')
        f.loc[te, 'pm'] = mod.design(f[te], 'margin').values @ bm.values
        f.loc[te, 'pt'] = mod.design(f[te], 'total').values @ bt.values
        f.loc[te, 'sd'] = sd
    mod.TOTAL_MODE = 'ols'
    return f


def recalibrate(f, ym, yt):
    """1b: + (sum of earlier same-season errors) / (n + 100), games ordered by date."""
    f = f.sort_values(['season', 'date' if 'date' in f else 'gameday']).copy()
    em, et = (ym - f.pm), (yt - f.pt)
    for col, e in (('pm', em), ('pt', et)):
        e = e.where(e.notna(), 0.0); n = e.ne(0).astype(float)
        cs = e.groupby(f.season).cumsum() - e; cn = n.groupby(f.season).cumsum() - n
        f[col] = f[col] + cs / (cn + 100)
    return f


def classifier(mod, f, kind, window, P):
    from sklearn.ensemble import HistGradientBoostingClassifier
    first = cfb.FIRST if mod is cfb else nfl.FIRST_FIT
    X = mod.design(f, 'margin' if kind == 'spread' else 'total').drop(columns='const')
    if mod is cfb:
        ln = f.spread_med if kind == 'spread' else f.total_med
        lnl = f.spread_dk if kind == 'spread' else f.total_dk
        y_ = (f.home_score - f.away_score) + ln if kind == 'spread' else (f.home_score + f.away_score) - ln
        yl = (f.home_score - f.away_score) + lnl if kind == 'spread' else (f.home_score + f.away_score) - lnl
    else:
        ln = -f.spread_line if kind == 'spread' else f.total_line
        y_ = (f.result + ln) if kind == 'spread' else (f.total - ln); yl = y_
    prob = pd.Series(np.nan, f.index)
    for S in range(P[0][0], P[1][1] + 1):
        a = first if window is None else max(first, S - window)
        tr = f.season.between(a, S - 1) & y_.notna() & (y_ != 0) & X.notna().all(axis=1)
        te = (f.season == S) & X.notna().all(axis=1)
        if tr.sum() < 200 or not te.any():
            continue
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=50, random_state=0)
        m.fit(X[tr].values, (y_[tr] > 0).values)
        prob[te] = m.predict_proba(X[te].values)[:, 1]
    out = {}
    for thr in (0.53, 0.55, 0.58):
        r = []
        for per in P:
            yy = yl if (mod is cfb and per == cfb.LATE) else y_
            s = f.season.between(*per) & prob.notna() & yy.notna() & (yy != 0) & ((prob >= thr) | (prob <= 1 - thr))
            pick = prob[s] >= thr
            win = np.where(pick, yy[s] > 0, yy[s] < 0)
            r.append((int(win.sum()), int(s.sum()), float(pick.mean()) if s.any() else float('nan')))
        out[thr] = r
    return out


def line_rows(tag, mod, f, P):
    for kind in ('spread', 'total'):
        for t in (0, 2, 4):
            a, b = mod.bets(f, P[0], kind, t), mod.bets(f, P[1], kind, t)
            p = cfb.pval(a[0] + b[0], a[1] + b[1])
            ok = a[1] >= 100 and b[1] >= 100 and a[0] / max(a[1], 1) >= .524 and b[0] / max(b[1], 1) >= .524 and p < .05
            txt.append(f"  {kind:6s} edge {t}+  {a[0]}/{a[1]} = {a[0] / max(a[1], 1):.1%} | {b[0]}/{b[1]} = {b[0] / max(b[1], 1):.1%} | p={p:.3f} | "
                       f"{'TESTED PICK' if ok else 'LEAN':11s} | {'home' if kind == 'spread' else 'Over'} share {a[2]:.0%} / {b[2]:.0%}")
            res[f'{tag}|{kind}|{t}'] = dict(p1=a[:2], p2=b[:2], p=p, passes=ok)


def run(name, mod, f, P, ym, yt, mw, tw, tmode, era):
    txt.append(f'\n===== {name} (periods {P[0][0]}-{P[0][1]} / {P[1][0]}-{P[1][1]})')
    cur = base_preds(mod, f, mw, tw, tmode)
    txt.append('CURRENT card model:'); line_rows(f'{name}|current', mod, cur, P)
    e1 = base_preds(mod, f, mw, tw, tmode, era_start=era)
    txt.append(f'1a ERA FIT (era from {era}):'); line_rows(f'{name}|1a', mod, e1, P)
    r1 = recalibrate(cur, ym(cur), yt(cur))
    txt.append('1b IN-SEASON RECALIBRATION:'); line_rows(f'{name}|1b', mod, r1, P)
    for win, lab in ((None, 'all earlier seasons'), (3, 'last 3 seasons')):
        txt.append(f'2 CLASSIFIER, trained on {lab}:')
        for kind in ('spread', 'total'):
            c = classifier(mod, f, kind, win, P)
            for thr, (a, b) in c.items():
                p = cfb.pval(a[0] + b[0], a[1] + b[1])
                ok = a[1] >= 100 and b[1] >= 100 and a[0] / max(a[1], 1) >= .524 and b[0] / max(b[1], 1) >= .524 and p < .05
                txt.append(f"  {kind:6s} chance {round(thr * 100)}%+  {a[0]}/{a[1]} = {a[0] / max(a[1], 1):.1%} | {b[0]}/{b[1]} = {b[0] / max(b[1], 1):.1%} | "
                           f"p={p:.3f} | {'TESTED PICK' if ok else 'LEAN':11s} | {'home' if kind == 'spread' else 'Over'} share {a[2]:.0%} / {b[2]:.0%}")
                res[f'{name}|2|{lab}|{kind}|{thr}'] = dict(p1=a[:2], p2=b[:2], p=p, passes=ok)


cfb.EXTRA[:] = cfb.EXTRA_ALL
run('NFL', nfl, nfl.build(4), ((2021, 2023), (2024, 2026)), lambda f: f.result, lambda f: f.total, None, None, 'ols', 2022)
run('COLLEGE', cfb, college_frame(), ((2020, 2022), (2023, 2026)), lambda f: f.home_score - f.away_score,
    lambda f: f.home_score + f.away_score, None, 3, 'median', 2023)
open(os.path.join(HERE, 'results', 'approaches.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'approaches.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
