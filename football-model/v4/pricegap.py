"""v4 idea C live: moneyline-implied margin vs the spread (v4/PROTOCOL.md). Fit on all completed seasons.
NFL mapping: nflverse closing moneylines/spreads. CFB mapping: Bovada 2021-22 + DraftKings 2023+ (CFBD)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'v3'))
import data, grade  # noqa

_C = {}


def _lg(h, a):
    ih, ia = 1 / grade.dec([h])[0], 1 / grade.dec([a])[0]
    p = min(max(ih / (ih + ia), 0.005), 0.995)
    return np.log(p / (1 - p))


def _fit(league):
    if league in _C:
        return _C[league]
    if league == 'nfl':
        g = data.nfl_games().dropna(subset=['home_moneyline', 'away_moneyline', 'spread_line', 'result'])
        x = np.array([_lg(h, a) for h, a in zip(g.home_moneyline, g.away_moneyline)]); y = g.spread_line.values
    else:
        rows = []
        for yr in range(2021, pd.Timestamp.now().year + 1):
            L = data.cfb_lines(yr)
            bk = 'Bovada' if yr <= 2022 else 'DraftKings'
            rows.append(L[L.provider == bk].dropna(subset=['spread', 'home_ml', 'away_ml']))
        M = pd.concat(rows)
        x = np.array([_lg(h, a) for h, a in zip(M.home_ml, M.away_ml)]); y = -M.spread.values
    _C[league] = np.polyfit(x, y, 3)
    return _C[league]


def gap(league, home_ml, away_ml, home_margin_line):
    """Returns (implied home margin, gap). gap > 0: moneyline rates the home team better than the spread does."""
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in (home_ml, away_ml, home_margin_line)):
        return None, None
    imp = float(np.polyval(_fit(league), _lg(home_ml, away_ml)))
    return imp, imp - home_margin_line
