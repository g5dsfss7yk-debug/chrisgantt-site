"""V2 NFL model, built from scratch (Nov 15 2026). Shares no code with the old model.

Each team carries exponentially weighted play-by-play ratings (offense and defense EPA/play,
success rate, explosive rate, turnovers, special teams), updated after every game and pulled
toward average at each new season. A ridge regression turns the home-minus-away ratings, rest,
QB change and the line into a predicted margin and total. Walk-forward: every season is
predicted by a model fit only on earlier seasons.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nflmodel import data, teams

STATS = ["epa", "sr", "explosive", "giveaways", "st_epa", "plays", "press", "rz", "c_epa", "c_sr", "c_explosive"]   # press: (sacks+QB hits)/dropback; rz: red-zone TD rate
TOTAL_SKIP = {"rz", "c_epa", "c_sr", "c_explosive"}   # spreads-only inputs (v2/test_four.py, v2/test_methods.py)
SPREAD_SKIP = {"epa", "sr", "explosive"}   # spreads use the competitive-play versions (c_*) instead (Chris, Nov 23)
HALF_LIFE = 4          # games (picked on 2015-22 only, see v2/grid.py)
CARRY = 0.65           # share of last season kept at a new season
FIRST_TEST = 2015
SKIP_NAN = ("_rz", "_sec_per_play", "_neutral_pass", "_no_huddle")
# Options tested Nov 23 (v2/test_three.py); off unless the test earned them
OPP_ADJ = 0.0          # 0..1: share of the opponent's strength taken out of each game's stats
ST_SPLIT = False       # special teams split into FG, punting, punt return, kick return, kick coverage
RUSH_OUT = False       # share of a defense's recent sacks + QB hits listed Out/Doubtful that week (spread + total)
QB_VAL = False         # listed starter's own career EPA/play (any team), shrunk for few plays (spread + total)
QB_VAL_SPREAD = True   # same, spreads only: ON since Nov 23 (with rz): spread edge 1+ 54.9% / 54.9% vs 52.8% / 54.1%
REF_TOT = False        # crew chief's past (total - line), totals only - NOTE: games.csv posts the referee after the game
PACE = False           # seconds per play, neutral-situation pass rate, no-huddle rate
RZ = False             # red-zone touchdown rate (TDs per trip inside the 20)
SKILL_OUT = ""         # "": off; "all": one share of RB+WR+TE yards Out/Doubtful; "split": RB, WR, TE separately
SKILL_KINDS = ("spread", "total")
RATING = "ewm"         # "ewm": weighted average of recent games; "median": median of the last 8 games (Nov 23 test)
COMPETITIVE = False    # EPA / success / explosive from win-prob 10-90% plays only, EPA capped at +/-3 (Nov 23 test)
CLIP = None            # cap the fit target (margin or total minus the line) at +/- this many points (Nov 23 test)
RUSH_OUT_TOTAL = True  # same, totals only: ON since Nov 23 (Chris) - totals 53.5% / 51.0% vs 53.2% / 50.5% without
SCALE = True           # standardize features before the ridge (without it the ridge zeroes the rate stats)
ALPHA = {"spread": 10.0, "total": 10.0}   # picked on 2015-22 only (v2/improve.py)
OUTDOOR_WIND = 8.3     # mean outdoor wind 2009-26 (mph): used when a game's wind is still unknown
WIND_FROM = 2019       # first season where games.csv misses wind for outdoor games


def fill_wind(d: pd.DataFrame) -> pd.DataFrame:
    """games.csv has no wind for many outdoor games (46% of 2022, every game since 2026 week 5).
    Fill from the play-by-play weather text, then the kickoff forecast for unplayed games."""
    d = d.copy()
    try:
        w = data.load_game_weather(range(WIND_FROM, data.current_season() + 1))
        txt = w.set_index("game_id")["weather"].str.extract(r"Wind:\s*[A-Za-z]*\s*(\d+)")[0].astype(float)
        d["wind"] = d["wind"].fillna(d["game_id"].map(txt))
    except Exception as e:
        print(f"warning: no play-by-play weather ({e})")
    try:
        f = data.load_forecasts()
        if len(f):
            d["wind"] = d["wind"].fillna(d["game_id"].map(f.drop_duplicates("game_id").set_index("game_id")["wind"]))
    except Exception as e:
        print(f"warning: no forecasts ({e})")
    return d


def team_games() -> pd.DataFrame:
    g = data.load_games()
    g = g[g["game_type"].isin(["REG", "WC", "DIV", "CON", "SB"])].copy()
    p = data.load_team_pbp(range(2008, data.current_season() + 1))
    p["team"] = p["team"].map(teams.franchise)
    p["press"] = (p["sacks"] + p["qb_hits"]) / p["dropbacks"].clip(lower=1)   # o_press = line allows, d_press = defense makes
    p["rz"] = p["rz_tds"] / p["rz_trips"].where(p["rz_trips"] > 0)                 # NaN with no trips: skipped
    # competitive plays only (win prob 10-90%, EPA capped +/-3): c_epa, c_sr, c_explosive - used by spreads
    from v2 import extra_data
    c = extra_data.competitive(range(2008, data.current_season() + 1))
    c["team"] = c["team"].map(teams.franchise)
    p = p.merge(c.groupby(["game_id", "team"], as_index=False).mean(), on=["game_id", "team"], how="left")
    for k in ("epa", "sr", "explosive"):
        p[f"c_{k}"] = p[f"c_{k}"].fillna(p[k])
        if COMPETITIVE:          # test switch: replace the all-play versions everywhere
            p[k] = p[f"c_{k}"]
    if ST_SPLIT:
        from v2 import extra_data
        x = extra_data.special_teams(range(2008, data.current_season() + 1))
        x["team"] = x["team"].map(teams.franchise)
        x = x.groupby(["game_id", "team"], as_index=False).sum()
        p = p.merge(x, on=["game_id", "team"], how="left")
        p[extra_data.ST_UNITS] = p[extra_data.ST_UNITS].fillna(0)
    g["home_fr"], g["away_fr"] = g["home_team"].map(teams.franchise), g["away_team"].map(teams.franchise)
    return g, p


def ratings(g: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Pre-game ratings for both teams of every game (only earlier games are used)."""
    p = p.set_index(["game_id", "team"])
    a = 1 - 0.5 ** (1 / HALF_LIFE)
    st, season_of, mean, hist = {}, {}, {}, {}
    rows = []
    g = g.sort_values(["gameday", "gametime", "game_id"])
    for r in g.itertuples(index=False):
        rec = {"game_id": r.game_id}
        for side, t in (("home", r.home_fr), ("away", r.away_fr)):
            if t in st and season_of[t] != r.season and RATING == "median":
                season_of[t] = r.season                 # median of the last 8 games runs across seasons
            elif t in st and season_of[t] != r.season:  # new season: pull toward average
                st[t] = {k: CARRY * v + (1 - CARRY) * mean.get(k, v) for k, v in st[t].items()}
                season_of[t] = r.season
            s = st.get(t, {})
            for k, v in s.items():
                rec[f"{side}_{k}"] = v
            rec[f"{side}_n"] = s.get("n", 0)
        rows.append(rec)
        if pd.isna(r.result):
            continue
        snap = {t: dict(st.get(t, {})) for t in (r.home_fr, r.away_fr)}   # ratings before this game
        for t, o in ((r.home_fr, r.away_fr), (r.away_fr, r.home_fr)):
            if (r.game_id, t) not in p.index or (r.game_id, o) not in p.index:
                continue
            off, dfn = p.loc[(r.game_id, t)], p.loc[(r.game_id, o)]
            obs = {f"o_{k}": off[k] for k in STATS} | {f"d_{k}": dfn[k] for k in STATS}
            pts_for = r.home_score if t == r.home_fr else r.away_score
            pts_ag = r.away_score if t == r.home_fr else r.home_score
            obs |= {"pf": pts_for, "pa": pts_ag}
            if OPP_ADJ and snap[o].get("n", 0) >= 3:
                # credit for a stat is relative to what this opponent usually allows / produces
                mirror = {f"o_{k}": f"d_{k}" for k in STATS} | {f"d_{k}": f"o_{k}" for k in STATS} | {"pf": "pa", "pa": "pf"}
                for k, m in mirror.items():
                    if m in snap[o] and m in mean and not pd.isna(obs[k]):
                        obs[k] = obs[k] - OPP_ADJ * (snap[o][m] - mean[m])
            s = st.setdefault(t, {})
            season_of.setdefault(t, r.season)
            if RATING == "median":
                h = hist.setdefault(t, {})
                for k, v in obs.items():
                    if pd.isna(v):
                        continue
                    h.setdefault(k, []).append(float(v))
                    h[k] = h[k][-8:]
                    s[k] = float(np.median(h[k]))
                    mean[k] = float(v) if k not in mean else 0.995 * mean[k] + 0.005 * float(v)
                s["n"] = s.get("n", 0) + 1
                continue
            for k, v in obs.items():
                if pd.isna(v) and k.endswith(SKIP_NAN):
                    continue                          # e.g. no red-zone trip: no information, keep the rating
                v = 0.0 if pd.isna(v) else float(v)
                s[k] = v if k not in s else (1 - a) * s[k] + a * v
                mean[k] = v if k not in mean else 0.995 * mean[k] + 0.005 * v
            s["n"] = s.get("n", 0) + 1
    return pd.DataFrame(rows)


def build() -> pd.DataFrame:
    g, p = team_games()
    rt = ratings(g, p)
    d = fill_wind(g.merge(rt, on="game_id"))
    if QB_VAL or QB_VAL_SPREAD:
        from v2 import extra_data
        v = extra_data.qb_values()
        for side in ("home", "away"):
            d[f"{side}_qb_val"] = extra_data.qb_value_at(v, d[f"{side}_qb_id"], d["season"], d["week"])
    if REF_TOT:
        from v2 import extra_data
        d["ref_tot"] = extra_data.referee_totals(d)
    if SKILL_OUT:
        from v2 import extra_data
        so = extra_data.skill_out_all()
        cols = ["rb_out", "wr_out", "te_out", "skill_out"]
        for side in ("home", "away"):
            d = d.merge(so.rename(columns={"team": f"{side}_fr"} | {c: f"{side}_{c}" for c in cols}),
                        on=["season", "week", f"{side}_fr"], how="left")
            d[[f"{side}_{c}" for c in cols]] = d[[f"{side}_{c}" for c in cols]].fillna(0)
    if RUSH_OUT or RUSH_OUT_TOTAL:
        from v2 import extra_data
        ro = extra_data.rush_out_all()
        for side in ("home", "away"):
            d = d.merge(ro.rename(columns={"team": f"{side}_fr", "rush_out": f"{side}_rush_out"}),
                        on=["season", "week", f"{side}_fr"], how="left")
            d[f"{side}_rush_listed"] = d[f"{side}_rush_out"].notna()   # False: no Out/Doubtful report found
            d[f"{side}_rush_out"] = d[f"{side}_rush_out"].fillna(0)
    n = data.load_nfelo()[["season", "week", "home_fr", "home_line_open", "total_line_open"]]
    d = d.merge(n, on=["season", "week", "home_fr"], how="left")
    d["spread_open"] = -d["home_line_open"]           # + = home favored, like spread_line
    d["total_open"] = d["total_line_open"]
    # QB change vs the team's previous starter (same season)
    d = d.sort_values("gameday").reset_index(drop=True)
    last, hq, aq = {}, [], []
    for r in d.itertuples(index=False):
        for side, fr, q, out in (("home", r.home_fr, r.home_qb_id, hq), ("away", r.away_fr, r.away_qb_id, aq)):
            if pd.isna(q):                    # starter not listed yet (future weeks): no change, keep the last one
                out.append(0)
                continue
            out.append(int(last.get((r.season, fr), q) != q))
            last[(r.season, fr)] = q
    d["home_qb_change"], d["away_qb_change"] = hq, aq
    return d


def X(d: pd.DataFrame, line: pd.Series, kind: str) -> pd.DataFrame:
    f = {}
    for k in STATS:
        if (kind == "total" and k in TOTAL_SKIP) or (kind == "spread" and k in SPREAD_SKIP):
            continue
        if kind == "spread":
            f[f"off_{k}"] = d[f"home_o_{k}"] - d[f"away_o_{k}"]
            f[f"def_{k}"] = d[f"home_d_{k}"] - d[f"away_d_{k}"]
            f[f"m_{k}"] = (d[f"home_o_{k}"] - d[f"away_d_{k}"]) - (d[f"away_o_{k}"] - d[f"home_d_{k}"])
        else:
            f[f"sum_o_{k}"] = d[f"home_o_{k}"] + d[f"away_o_{k}"]
            f[f"sum_d_{k}"] = d[f"home_d_{k}"] + d[f"away_d_{k}"]
    if kind == "spread":
        f["pts"] = (d["home_pf"] - d["home_pa"]) - (d["away_pf"] - d["away_pa"])
        f["rest"] = (d["home_rest"] - d["away_rest"]).clip(-7, 7)
        f["qb"] = d["home_qb_change"] - d["away_qb_change"]
        f["neutral"] = (d["location"] == "Neutral").astype(int)
        if RUSH_OUT:
            f["rush_out"] = d["home_rush_out"] - d["away_rush_out"]
        if QB_VAL or QB_VAL_SPREAD:
            f["qb_val"] = d["home_qb_val"] - d["away_qb_val"]
    else:
        f["pts"] = d["home_pf"] + d["home_pa"] + d["away_pf"] + d["away_pa"]
        f["wind"] = d["wind"].fillna(OUTDOOR_WIND).where(~d["roof"].isin(["dome", "closed"]), 0)
        f["dome"] = d["roof"].isin(["dome", "closed"]).astype(int)
        f["qb"] = d["home_qb_change"] + d["away_qb_change"]
        if RUSH_OUT or RUSH_OUT_TOTAL:
            f["rush_out"] = d["home_rush_out"] + d["away_rush_out"]
        if QB_VAL:
            f["qb_val"] = d["home_qb_val"] + d["away_qb_val"]
        if REF_TOT:
            f["ref_tot"] = d["ref_tot"]
    if SKILL_OUT and kind in SKILL_KINDS:
        for c in (["skill_out"] if SKILL_OUT == "all" else ["rb_out", "wr_out", "te_out"]):
            f[c] = d[f"home_{c}"] - d[f"away_{c}"] if kind == "spread" else d[f"home_{c}"] + d[f"away_{c}"]
    f["line"] = line
    x = pd.DataFrame(f).fillna(0)
    early = (d[["home_n", "away_n"]].fillna(0).min(axis=1) < 3).astype(float)
    # early in a team's history the ratings are thin: let the line carry more
    for c in x:
        if c != "line":
            x[c] = x[c] * (1 - 0.5 * early)
    return x


def fit(train: pd.DataFrame, kind: str, line_col: str):
    y = train["result"] if kind == "spread" else train["total"]
    if CLIP is not None:   # a 35-point blowout counts no more than a CLIP-point miss vs the line
        y = train[line_col] + (y - train[line_col]).clip(-CLIP, CLIP)
    ridge = Ridge(alpha=ALPHA[kind])
    m = make_pipeline(StandardScaler(), ridge) if SCALE else ridge
    return m.fit(X(train, train[line_col], kind), y)


def walk_forward(d: pd.DataFrame, kind: str, line_col: str) -> pd.DataFrame:
    out = []
    done = d[d["result"].notna() & d[line_col].notna() & (d["season"] >= 2009)]
    for s in range(FIRST_TEST, int(d["season"].max()) + 1):
        tr = done[done["season"] < s]
        if tr.empty:
            continue
        te = d[(d["season"] == s) & d[line_col].notna()].copy()
        m = fit(tr, kind, line_col)
        te["pred"] = m.predict(X(te, te[line_col], kind))
        out.append(te)
    return pd.concat(out)
