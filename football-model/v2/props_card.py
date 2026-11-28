"""v2 props + alternate lines vs DraftKings for upcoming games. Prints every DK rung where the
v2 chance beats DK's implied chance, with both numbers. Tested: v2/test_props.py, v2/test_alt.py
(calibration 2023-26). Whether these beat DK's prices is NOT tested yet (needs graded DK rungs:
saved to picks/rungs_v2/).

    python v2/props_card.py --before 13:05 [--min-edge 0.03]
"""
import sys as _sys
_sys.exit('RETIRED Nov 28 2026 - Chris: "There should be no old models picking anything". Use football-model/core/ (core/HANDOFF.md).')
import argparse, re, sys, unicodedata
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import nfl, props
from nflmodel import odds, data, teams
from run import NICK

MK = {"player_pass_yds_alternate": "passing_yards", "player_rush_yds_alternate": "rushing_yards",
      "player_reception_yds_alternate": "receiving_yards", "player_receptions_alternate": "receptions",
      "player_rush_reception_yds_alternate": "rush_rec_yards", "player_pass_tds_alternate": "passing_tds",
      "player_anytime_td": "anytime_td"}
# calibration fixes from v2/test_props.py (2023-26: model minus actual in the 20-90% range)
FIX = {"passing_yards": -0.045, "passing_tds": -0.03}
OUT = data.ROOT / "picks" / "rungs_v2"


def norm(n):
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'\-]", "", n)
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", n).strip()


ap = argparse.ArgumentParser(); ap.add_argument("--before"); ap.add_argument("--week", type=int)
ap.add_argument("--min-edge", type=float, default=0.03)
ap.add_argument("--cached", action="store_true", help="use saved DK prices, spend no API credits")
a = ap.parse_args()
s = props.load()
# same inputs as training: career history (games count, weighted averages run across seasons),
# kept to players who have played this season. (Before Nov 15 PM this used this season only,
# so every player looked like a rookie to the model - fixed.)
nxt = props.next_game(s[s.season >= 2015])
nxt = nxt[nxt.player_id.isin(s.loc[s.season == data.current_season(), "player_id"])]
nxt["key"] = nxt["player_display_name"].map(norm)
d = nfl.build()
season = data.current_season()
wk = a.week or int(d[(d.season == season) & d.result.isna()]["week"].min())
done = d[d.result.notna() & (d.season >= 2009)]
ms = nfl.fit(done[done.spread_open.notna()], "spread", "spread_open")
mt = nfl.fit(done[done.total_line.notna()], "total", "total_line")
rs, rt = np.load(Path(__file__).parent / "resid_spread.npy"), np.load(Path(__file__).parent / "resid_total.npy")
g = d[(d.season == season) & (d.week == wk) & d.result.isna()]
if a.before:
    g = g[g.gametime.astype(str) <= a.before]
inj = data.load_injuries([season])
inj = inj[inj.week == wk]
OUTK = set(inj[inj.report_status.isin(["Out", "Doubtful"]) | inj.get("gameday_inactive", False).fillna(False).astype(bool)]["full_name"].map(norm))
cur = s[s.season == season]
# freed-up targets/carries (Nov 23): teammates Out/Doubtful on the report or inactive today
_ids = inj[inj.report_status.isin(["Out", "Doubtful"]) | inj.get("gameday_inactive", False).fillna(False).astype(bool)]
_name_id = cur.drop_duplicates("player_id").assign(k=lambda x: x.player_display_name.map(norm)).set_index(["k", "team"]).player_id
_ids = _ids.assign(team=_ids.team.map(teams.franchise), k=_ids.full_name.map(norm))
_ids["player_id"] = _ids["gsis_id"].where(_ids["gsis_id"].notna(),
                                          [_name_id.get((k, t)) for k, t in zip(_ids.k, _ids.team)])
_games = pd.concat([pd.DataFrame({"game_id": g.game_id, "team": g.home_team.map(teams.franchise), "season": g.season,
                                  "week": g.week, "gameday": g.gameday}),
                    pd.DataFrame({"game_id": g.game_id, "team": g.away_team.map(teams.franchise), "season": g.season,
                                  "week": g.week, "gameday": g.gameday})])
WXG = props.game_weather().set_index("game_id") if props.USE_WX else None
VAC = props.vacated_next(s[s.season >= 2015], _ids.dropna(subset=["player_id"])[["team", "player_id"]].drop_duplicates(), _games)
GRP = {"RB": "RB", "WR": "WR/TE", "TE": "WR/TE", "QB": "QB"}


def returning(team):
    """Teammates (by position group) who had a real role this season, missed one of the team's
    last 3 games, and are not Out/Doubtful/inactive today: their return can shrink others' roles."""
    t = cur[cur.team == team]
    last3 = sorted(t.week.unique())[-3:]
    back = {}
    for pid, x in t.groupby("player_id"):
        nm = x.player_display_name.iloc[0]
        if x.snap_pct.max() >= 0.40 and not set(last3) <= set(x.week) and norm(nm) not in OUTK:
            back.setdefault(GRP.get(x.position.iloc[0], "?"), []).append(nm)
    return back


import json
CAL = json.load(open(Path(__file__).parent / "calib.json"))


def tested(market, p):
    """The 2023-26 hit rate of rungs the model gave a chance in the same 5-point range."""
    c = CAL[market]
    i = int(np.clip(np.searchsorted(c["edges"], p, side="left") - 1, 0, len(c["hit"]) - 1))
    # above the top tested range (too few cases, e.g. star TDs): use the highest range that was
    # tested - the real rate there is at least as high, so this errs low, not high
    j = i
    while j > 0 and c["hit"][j] is None and p > c["edges"][j]:
        j -= 1
    return c["hit"][j] if c["hit"][j] is not None and (j == i or p > c["edges"][j]) else c["hit"][i]


models = {}
hist = props.history(s[s.season >= 2015].copy())
import pickle
CACHE = Path(__file__).parent / f"props_models_vacwxturf_{pd.Timestamp.now('UTC'):%Y%m%d}.pkl"   # refit once a day
if CACHE.exists():
    models = pickle.load(open(CACHE, "rb"))
else:
    for mk in set(MK.values()):
        m = props.StatModel(mk); x = m.rows(hist); models[mk] = m.fit(x)
    try:
        pickle.dump(models, open(CACHE, "wb"))
    except Exception:
        CACHE.unlink(missing_ok=True)
odds.TTL = 10**9 if a.cached else 0
evs = odds.events("nfl")
allrows = []
for r in g.sort_values(["gameday", "gametime"]).itertuples(index=False):
    e = evs[evs.home.str.contains(NICK[r.home_team]) & evs.away.str.contains(NICK[r.away_team])]
    if e.empty:
        continue
    j = odds._get(f"/sports/americanfootball_nfl/events/{e.id.iloc[0]}/odds", bookmakers="draftkings",
                  markets=",".join(list(MK) + ["alternate_spreads", "alternate_totals", "spreads", "totals"]),
                  oddsFormat="american")
    bk = j.get("bookmakers", [])
    if not bk:
        print(f"{r.away_team} @ {r.home_team}: no DK prices"); continue
    mkts = {m["key"]: m["outcomes"] for m in bk[0]["markets"]}
    sp = next(o for o in mkts["spreads"] if NICK[r.home_team] in o["name"])
    dk_line, tot = -sp["point"], mkts["totals"][0]["point"]
    row = pd.DataFrame([r._asdict()])
    pm = ms.predict(nfl.X(row, row["spread_open"].fillna(dk_line), "spread"))[0]
    pt = mt.predict(nfl.X(row, pd.Series([tot]), "total"))[0]
    out = []
    for o in mkts.get("alternate_spreads", []):
        home = NICK[r.home_team] in o["name"]
        need = -o["point"] - pm if home else o["point"] + pm       # residual must beat this
        p = 1 - np.searchsorted(rs, need, side="right") / len(rs) if home else np.searchsorted(rs, -o["point"] - pm + 0, side="left") / len(rs)
        if not home:   # away covers if result < o["point"]  (result = home margin)
            p = np.searchsorted(rs, o["point"] - pm, side="left") / len(rs)
        out.append(("alt spread", f"{r.home_team if home else r.away_team} {o['point']:+g}", p, o["price"]))
    for o in mkts.get("alternate_totals", []):
        over = o["name"] == "Over"
        p = 1 - np.searchsorted(rt, o["point"] - pt, side="right") / len(rt)
        out.append(("alt total", f"{o['name']} {o['point']:g}", p if over else 1 - p, o["price"]))
    teams_here = {teams.franchise(r.home_team), teams.franchise(r.away_team)}
    for k, mk in MK.items():
        for o in mkts.get(k, []):
            if o["name"] not in ("Over", "Yes"):
                continue
            pl = nxt[(nxt.key == norm(o.get("description"))) & nxt.team.isin(teams_here)]
            if pl.empty:
                continue
            pl = pl.iloc[[0]].copy()
            if pl.key.iloc[0] in OUTK:
                continue
            back = [n for n in returning(pl.team.iloc[0]).get(GRP.get(pl.position.iloc[0]), []) if norm(n) != pl.key.iloc[0]]
            t_home = pl.team.iloc[0] == teams.franchise(r.home_team)
            pl["spread_for"] = dk_line if t_home else -dk_line
            pl["pts"] = tot / 2 + pl["spread_for"] / 2
            pl["home"] = int(t_home)
            opp = teams.franchise(r.away_team) if t_home else teams.franchise(r.home_team)
            pl = props.with_opponent(pl, s, opp)   # opposing defense: yards/TDs allowed, QB pressure
            pl = props._vac_pos(pl.merge(VAC.drop(columns="game_id"), on="team", how="left"))
            wxr = WXG.loc[r.game_id] if WXG is not None and r.game_id in WXG.index else {}
            for cc in (props.WX if WXG is not None else []):
                pl[cc] = wxr[cc] if len(wxr) else np.nan
            pl["turf"] = props.turf_of(r.game_id)
            freed = (f"  [FREED UP: {pl.vac_t_pos.iloc[0]:.0f} targets / {pl.vac_c_pos.iloc[0]:.0f} carries at his position, in the model]"
                     if pl.vac_t_pos.iloc[0] >= 4 or pl.vac_c_pos.iloc[0] >= 4 else "")
            rung = 1 if mk == "anytime_td" else int(np.ceil(o.get("point", 0.5)))
            pred = models[mk].predict(pl)[0]
            p = props.wx_adjust(mk, models[mk].p_reach(pred, rung), wxr)
            lab = f"{o['description']} {'anytime TD' if mk == 'anytime_td' else f'{rung}+ {mk}'}"
            out.append((mk, lab + freed + (f"  [ROLE CHECK: {', '.join(back)} back]" if back else ""), p, o["price"]))
    print(f"\n=== {r.away_team} @ {r.home_team}  (DK {r.home_team} {-dk_line:+g}, total {tot:g}) ===")
    df = pd.DataFrame(out, columns=["market", "bet", "v2", "price"])
    df["model"] = df.v2
    # the alt-spread table is for the home side; an away number uses its mirror
    hm = NICK[r.home_team]
    df["v2"] = [(None if tested(m, 1 - v) is None else 1 - tested(m, 1 - v)) if (m == "alt spread" and not b.startswith(r.home_team)) else tested(m, v)
                for m, v, b in zip(df.market, df.v2, df.bet)]
    df = df[df.v2.notna()]
    df["dk"] = df.price.map(odds.implied)
    df["edge"] = df.v2 - df.dk
    df["game"] = f"{r.away_team}@{r.home_team}"
    allrows.append(df)
    show = df[(df.edge >= a.min_edge) & (df.v2 >= 0.35)].sort_values("edge", ascending=False).head(12)
    for x in show.itertuples():
        print(f"  {x.bet.split('  [')[0]:42.42s} {x.price:+5d}  tested {x.v2:.0%}  DK {x.dk:.0%}  edge {x.edge:+.0%}" + ("  ROLE CHECK: " + x.bet.split("[ROLE CHECK: ")[1].rstrip("]") if "ROLE CHECK" in x.bet else "")
              + ("  FREED UP: " + x.bet.split("[FREED UP: ")[1].split("]")[0] if "FREED UP" in x.bet else ""))
if allrows:
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp.now("UTC").strftime("%Y%m%d_%H%M")
    pd.concat(allrows).assign(snapshot_utc=stamp).to_csv(OUT / f"{stamp}.csv", index=False)
