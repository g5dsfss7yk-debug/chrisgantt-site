"""Nov 15 2026 dig for a game-day edge. A short list of ideas fixed BEFORE looking (from betting
research, not scanned from this data), each graded at the closing line in three periods.
    PYTHONPATH=. python v2/dig.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from nflmodel import data, teams

g = data.load_games()
g = g[g.game_type.eq("REG") & g.result.notna() & g.spread_line.notna()].copy()
PER = [("1999-2014", g.season <= 2014), ("2015-22", g.season.between(2015, 2022)), ("2023-26", g.season >= 2023)]


def show(name, win, mask=None, need=None):
    out = []
    for lab, m in PER:
        w = win[m if mask is None else (m & mask)].dropna()
        out.append(f"{lab} {w.mean():.1%} of {len(w)}" if len(w) else f"{lab} -")
    print(f"  {name:44s} " + " | ".join(out) + (f"   needs {need}" if need else ""))


def roi(name, profit, mask):
    out = []
    for lab, m in PER:
        p = profit[m & mask].dropna()
        out.append(f"{lab} {p.mean():+.1%} of {len(p)}" if len(p) else f"{lab} -")
    print(f"  {name:44s} " + " | ".join(out))


# ---- 1. Teaser legs (Wong): every dog/favorite, 6 points, through 3 and 7
print("\n1. 6-point teaser legs, every team in the range (a 2-team -120 teaser needs 73.9% per leg)")
line, res = g.spread_line, g.result            # line + = home favored
dogm = np.where(line > 0, -res, res)           # underdog's margin
dl = line.abs()
dog_win = pd.Series(np.where(dogm + dl + 6 == 0, np.nan, dogm + dl + 6 > 0), index=g.index)
fav_win = pd.Series(np.where(-dogm - dl + 6 == 0, np.nan, -dogm - dl + 6 > 0), index=g.index)
home_dog = line < 0
for lo, hi in ((1.5, 2.5), (3, 3), (3.5, 6.5)):
    show(f"dog +{lo}..+{hi}", dog_win, dl.between(lo, hi))
show("dog +1.5..+2.5, total <= 44", dog_win, dl.between(1.5, 2.5) & (g.total_line <= 44))
show("dog +1.5..+2.5, total > 44", dog_win, dl.between(1.5, 2.5) & (g.total_line > 44))
show("HOME dog +1.5..+2.5", dog_win, dl.between(1.5, 2.5) & home_dog)
show("ROAD dog +1.5..+2.5", dog_win, dl.between(1.5, 2.5) & ~home_dog)
show("fav -7.5..-8.5", fav_win, dl.between(7.5, 8.5))
show("fav -7.5..-8.5, total <= 44", fav_win, dl.between(7.5, 8.5) & (g.total_line <= 44))

# ---- 2. Moneyline favorite-longshot bias, at the recorded closing prices
print("\n2. Moneyline profit per $1 at the closing price (2008+ only)")
def pay(ml): return np.where(ml > 0, ml / 100, 100 / ml.abs())
hp = pd.Series(np.where(res > 0, pay(g.home_moneyline), np.where(res < 0, -1, 0)), index=g.index).where(g.home_moneyline.notna())
ap = pd.Series(np.where(res < 0, pay(g.away_moneyline), np.where(res > 0, -1, 0)), index=g.index).where(g.away_moneyline.notna())
ml = pd.concat([g.home_moneyline, g.away_moneyline]); pr = pd.concat([hp, ap])
gg = pd.concat([g, g]); per2 = [(l, pd.concat([m, m])) for l, m in PER]
for lo, hi, lab in ((-10000, -400, "fav -400 or more"), (-399, -200, "fav -200..-399"), (-199, -120, "fav -120..-199"),
                    (-119, 119, "near even"), (120, 199, "dog +120..+199"), (200, 399, "dog +200..+399"), (400, 10000, "dog +400 or more")):
    m0 = ml.between(lo, hi)
    print(f"  {lab:44s} " + " | ".join(f"{l} {pr[m & m0].mean():+.1%} of {int((m & m0 & pr.notna()).sum())}" for l, m in per2[1:]))

# ---- 3. Market overreaction: closing line vs the market's own rating of the two teams
print("\n3. Fade the line when it strays from the market's own team ratings (ratings = ridge on the\n   season's earlier closing lines; needs 4+ weeks). Bet toward the rating. Needs 52.4%.")
g = g.sort_values(["gameday", "gametime"]).reset_index(drop=True)
PER = [("1999-2014", g.season <= 2014), ("2015-22", g.season.between(2015, 2022)), ("2023-26", g.season >= 2023)]
T = sorted(set(g.home_team) | set(g.away_team)); ix = {t: i for i, t in enumerate(T)}
dev = pd.Series(np.nan, index=g.index)
for s, gs in g.groupby("season"):
    for wk in sorted(gs.week.unique()):
        past = gs[(gs.week < wk) & (gs.week >= wk - 6)]
        cur = gs[gs.week == wk]
        if wk < 5 or len(past) < 40:
            continue
        def M(x):
            A = np.zeros((len(x), len(T) + 1))
            for i, r in enumerate(x.itertuples()):
                A[i, ix[r.home_team]], A[i, ix[r.away_team]] = 1, -1
                A[i, -1] = 0 if r.location == "Neutral" else 1
            return A
        m = Ridge(alpha=0.5, fit_intercept=False).fit(M(past), past.spread_line)
        dev[cur.index] = cur.spread_line - m.predict(M(cur))      # + = home priced stronger than its rating
act = g.result - g.spread_line
for th in (1, 2, 3, 4):
    w = pd.Series(np.where(act == 0, np.nan, np.sign(act) == -np.sign(dev)), index=g.index).where(dev.abs() >= th)
    show(f"line {th}+ pts from market rating: fade", w)

# ---- 4. nfelo (independent public model with QB adjustments) vs the closing line
print("\n4. nfelo's own line vs the closing line: bet nfelo's side. Needs 52.4%.")
n = data.load_nfelo()[["season", "week", "home_fr", "nfelo_home_line_close", "home_line_close"]]
g["home_fr"] = g.home_team.map(teams.franchise)
x = g.merge(n, on=["season", "week", "home_fr"], how="left")
e = -(x.nfelo_home_line_close) - x.spread_line                 # + = nfelo likes home more than the line
a = x.result - x.spread_line
PER = [("1999-2014", x.season <= 2014), ("2015-22", x.season.between(2015, 2022)), ("2023-26", x.season >= 2023)]
for th in (0.5, 1, 2, 3):
    w = pd.Series(np.where(a == 0, np.nan, np.sign(a) == np.sign(e)), index=x.index).where(e.abs() >= th)
    show(f"nfelo {th}+ pts from close", w)

# ---- 5. Actual 2-team teasers: every pair of qualifying dogs in the same week
print("\n5. 2-team 6-point teasers, every same-week pair of dogs +1.5..+2.5 (pushes dropped).\n   Break-even: 54.5% at -120, 56.5% at -130, 58.3% at -140.")
import itertools
g2 = data.load_games(); g2 = g2[g2.game_type.eq("REG") & g2.result.notna() & g2.spread_line.notna()].copy()
dl2 = g2.spread_line.abs(); dm = np.where(g2.spread_line > 0, -g2.result, g2.result)
g2["leg"] = np.where(dm + dl2 + 6 == 0, np.nan, dm + dl2 + 6 > 0)
for lab, q in (("all totals", dl2.between(1.5, 2.5)), ("total <= 44", dl2.between(1.5, 2.5) & (g2.total_line <= 44))):
    out = []
    for pl, lo, hi in (("1999-2014", 1999, 2014), ("2015-22", 2015, 2022), ("2023-26", 2023, 2026)):
        w = []
        for _, wk in g2[q & g2.season.between(lo, hi) & g2.leg.notna()].groupby(["season", "week"]):
            w += [a and b for a, b in itertools.combinations(wk.leg.astype(bool), 2)]
        out.append(f"{pl} {np.mean(w):.1%} of {len(w)}")
    print(f"  {lab:20s} " + " | ".join(out))
