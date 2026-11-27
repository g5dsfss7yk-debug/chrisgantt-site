"""v10 learning layer (v10/PROTOCOL.md): learns from graded DK prices (v8/prices/dk_props.csv).
python v10/learn.py  -> prints walk-forward Brier (model vs DK vs learned) and saves v10/learned.json (latest fit)."""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'v3'))
import grade
PRICES = os.path.join(ROOT, 'v8', 'prices', 'dk_props.csv')
OUT = os.path.join(HERE, 'learned.json')
lg = lambda p: np.log(np.clip(p, 1e-3, 1 - 1e-3) / (1 - np.clip(p, 1e-3, 1 - 1e-3)))


def rows():
    P = pd.read_csv(PRICES, dtype=str)
    P = P[P.over.notna() & (P.over != '') & P.result.notna() & ~P.result.isin(['', 'void'])].copy()
    P = P[pd.to_datetime(P.logged_at, utc=True) < pd.to_datetime(P.kickoff, utc=True)]
    P['y'] = (P.result.astype(float) > P.line.astype(float)).astype(float)
    p8 = pd.to_numeric(P.p_over_v8, errors='coerce'); p3 = pd.to_numeric(P.p_over_v3, errors='coerce')
    P['pm'] = p8.fillna(p3); P['pk'] = 1 / grade.dec(P.over.astype(float))
    P['day'] = pd.to_datetime(P.kickoff, utc=True).dt.tz_convert('America/Chicago').dt.strftime('%Y-%m-%d')
    return P[P.pm.notna()].reset_index(drop=True)


def fit(x):
    """Logistic regression by Newton steps (no extra packages); light ridge for stability."""
    X = np.column_stack([np.ones(len(x)), lg(x.pm.values), lg(x.pk.values)]); y = x.y.values
    w = np.array([0.0, 0.5, 0.5])
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w)); g = X.T @ (p - y) + 1.0 * w * [0, 1, 1]
        H = X.T @ (X * (p * (1 - p))[:, None]) + np.diag([1e-6, 1.0, 1.0])
        w = w - np.linalg.solve(H, g)
    return w


def predict(w, pm, pk):
    return 1 / (1 + np.exp(-(w[0] + w[1] * lg(pm) + w[2] * lg(pk))))


if __name__ == '__main__':
    P = rows(); days = sorted(P.day.unique())
    print(f'{len(P)} graded pre-kickoff DK prices over {len(days)} game day(s)')
    wf = []
    for i, d in enumerate(days):
        past, now = P[P.day < d], P[P.day == d]
        if len(past) < 100:
            continue
        w = fit(past); wf.append(now.assign(pl=predict(w, now.pm.values, now.pk.values)))
    if wf:
        W = pd.concat(wf); b = lambda q: float(np.mean((q - W.y) ** 2))
        print(f'walk-forward ({len(W)} prices): Brier model {b(W.pm):.4f} | DK {b(W.pk):.4f} | learned {b(W.pl):.4f}')
        ok = len(W) >= 300 and b(W.pl) < b(W.pm) and b(W.pl) < b(W.pk)
        print('learned chance PROVEN (beats model and DK over 300+)' if ok else 'learned chance NOT yet proven (needs 300+ walk-forward prices and to beat both)')
    else:
        ok = False; print('walk-forward not started: needs 100 graded prices from earlier days (first day is warm-up)')
    w = fit(P) if len(P) >= 30 else None
    if w is not None:
        print(f'latest fit on all {len(P)}: weight on model {w[1]:.2f}, on DK price {w[2]:.2f} (1 = trust fully)')
    json.dump(dict(n=len(P), coef=None if w is None else list(map(float, w)), proven=bool(ok)), open(OUT, 'w'), indent=1)
