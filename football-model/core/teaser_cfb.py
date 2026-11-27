"""College 6-pt teaser legs (core/PROTOCOL.md amendment 11). python core/teaser_cfb.py -> core/results/teaser_cfb.txt"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb

NEED = 0.739
L = cfb.lines(range(2014, 2027))
L = L.merge(cfb.data.cfb_lines(range(2014, 2027)).groupby('game_id').season.first().reset_index(), on='game_id')
L = L[L.home_score.notna() & L.away_score.notna()]


def legs(period, rule, size=None):
    x = L[L.season.between(*period)].copy()
    sp = x.spread_dk if period == cfb.LATE else x.spread_med          # home number: -7 = home favored
    x = x[sp.notna() & (sp != 0)]; sp = sp[x.index]
    margin = x.home_score - x.away_score
    # take the side and its points (positive = getting points)
    home_dog = sp > 0
    if rule in ('C1', 'C3'):
        pts = sp.abs(); m = np.where(home_dog, margin, -margin)       # the dog
    else:
        pts = -sp.abs(); m = np.where(home_dog, -margin, margin)      # the favorite
    sel = pd.Series(True, x.index)
    if rule == 'C3':
        sel = pts.between(1.5, 2.5)
    if rule == 'C4':
        sel = (-pts).between(7.5, 8.5)
    if size == '<7':
        sel &= sp.abs() < 7
    elif size == '7-14':
        sel &= sp.abs().between(7, 14)
    elif size == '>14':
        sel &= sp.abs() > 14
    r = (m + pts + 6)[sel.values]
    r = r[r != 0]
    return int((r > 0).sum()), int(len(r))


txt = ['College 6-point teaser legs (amendment 11). Needs 73.9% per leg (2-team at -120).']
res = {}
for rule, name in (('C1', 'every dog +6'), ('C2', 'every favorite +6'), ('C3', 'dogs +1.5..+2.5'), ('C4', 'favorites -7.5..-8.5')):
    e, l = legs(cfb.EARLY, rule), legs(cfb.LATE, rule)
    p = cfb.pval(e[0] + l[0], e[1] + l[1], NEED)
    ok = e[1] >= 100 and l[1] >= 100 and e[0] / max(e[1], 1) >= NEED and l[0] / max(l[1], 1) >= NEED and p < 0.05
    res[rule] = dict(early=e, late=l, p=p, passes=ok)
    txt.append(f"{rule} {name:22s} EARLY {e[0]}/{e[1]} = {e[0] / max(e[1], 1):.1%} | LATE {l[0]}/{l[1]} = {l[0] / max(l[1], 1):.1%} | p={p:.3f} | {'TESTED PICK' if ok else 'FAIL'}")
txt.append('\nInformation only (not a rule): by spread size')
for rule in ('C1', 'C2'):
    for sz in ('<7', '7-14', '>14'):
        e, l = legs(cfb.EARLY, rule, sz), legs(cfb.LATE, rule, sz)
        txt.append(f"  {rule} spread {sz:5s} EARLY {e[0]}/{e[1]} = {e[0] / max(e[1], 1):.1%} | LATE {l[0]}/{l[1]} = {l[0] / max(l[1], 1):.1%}")
os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
open(os.path.join(HERE, 'results', 'teaser_cfb.txt'), 'w').write('\n'.join(txt) + '\n')
json.dump(res, open(os.path.join(HERE, 'results', 'teaser_cfb.json'), 'w'), indent=1, default=float)
print('\n'.join(txt))
