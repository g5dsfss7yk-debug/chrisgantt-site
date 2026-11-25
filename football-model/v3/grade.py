"""Shared grading: hit rates vs the price, the protocol's pass/fail rule."""
import numpy as np
from math import comb


def dec(american):
    a = np.asarray(american, float)
    a = np.where(np.isnan(a), -110.0, a)
    return np.where(a > 0, 1 + a / 100, 1 + 100 / np.abs(a))


def binom_p_above_half(w, n):
    """One-sided P(X >= w) for X ~ Bin(n, 0.5)."""
    if n == 0:
        return 1.0
    if n > 1500:  # normal approx
        from math import erf, sqrt
        z = (w - 0.5 - n / 2) / sqrt(n / 4)
        return 0.5 * (1 - erf(z / sqrt(2)))
    return sum(comb(n, k) for k in range(w, n + 1)) / 2 ** n


def record(win, price=None, push=None):
    """win: bool array (True win). push: bool array (excluded). price: American odds per bet."""
    win = np.asarray(win, bool)
    push = np.zeros(len(win), bool) if push is None else np.asarray(push, bool)
    w, n = int((win & ~push).sum()), int((~push).sum())
    d = dec(price if price is not None else np.full(len(win), -110.0))[~push]
    profit = np.where(win[~push], d - 1, -1.0).sum()
    be = float(np.mean(1 / d)) if n else np.nan
    return {'w': w, 'n': n, 'pct': w / n if n else np.nan, 'be': be, 'roi': profit / n if n else np.nan}


def passes(early, late, kind='rate'):
    if kind == 'roi':
        return early['n'] >= 100 and late['n'] >= 100 and early['roi'] > 0 and late['roi'] > 0
    ok = early['n'] >= 100 and late['n'] >= 100 and early['pct'] >= early['be'] and late['pct'] >= late['be']
    p = binom_p_above_half(early['w'] + late['w'], early['n'] + late['n'])
    return bool(ok and p < 0.05)


def fmt(r):
    if not r['n']:
        return 'no bets'
    return f"{r['pct']:.1%} of {r['n']} (need {r['be']:.1%}, ROI {r['roi']:+.1%})"
