"""Props picks WITHOUT odds-API credits (Chris, Nov 23: stay on the free plan). For each player in the
chosen games: the TESTED chance (2023-26 hit rate of the model's range, v2/calib.json) of reaching the
standard numbers, and the DK price at which that chance breaks even. Chris compares it to the price on
his DraftKings slip: bet only if DK pays MORE than the break-even price.
Lines for team points: --line "CIN=-6" --total 54.5 (DK's numbers), else the schedule file's.
    PYTHONPATH=. python v2/props_free.py --team CIN --team WAS --line CIN=-6 --total 54.5"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from v2 import props
from nflmodel import data, teams

RUNGS = {"receiving_yards": [25, 40, 50, 60, 75, 100], "rushing_yards": [25, 40, 50, 60, 75, 100],
         "receptions": [2, 3, 4, 5, 6, 7], "passing_yards": [175, 200, 225, 250, 275, 300],
         "passing_tds": [1, 2, 3], "anytime_td": [1]}
FIX = {"passing_yards": -0.045, "passing_tds": -0.03}     # same calibration fixes as props_card.py
CAL = json.load(open(Path(__file__).parent / "calib.json"))


def tested(mk, p):
    c = CAL[mk]
    i = int(np.clip(np.searchsorted(c["edges"], p, side="left") - 1, 0, len(c["hit"]) - 1))
    while c["hit"][i] is None and i > 0:
        i -= 1
    return c["hit"][i]


def price(p):
    """American price that breaks even at chance p."""
    return -round(100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


ap = argparse.ArgumentParser()
ap.add_argument("--team", action="append", required=True)
ap.add_argument("--line", help="TEAM=-6 (DK spread for one team)")
ap.add_argument("--total", type=float)
ap.add_argument("--min", type=float, default=0.60, help="show rungs with a tested chance at least this")
a = ap.parse_args()

s = props.load()
season = data.current_season()
nxt = props.next_game(s[s.season >= 2015])
cur = s[s.season == season]
nxt = nxt[nxt.player_id.isin(cur.player_id)]
g = data.load_games()
g = g[(g.season == season) & g.result.isna()].sort_values("gameday")
T = [teams.franchise(t) for t in a.team]
game = g[g.home_team.map(teams.franchise).isin(T) | g.away_team.map(teams.franchise).isin(T)].iloc[0]
home, away = teams.franchise(game.home_team), teams.franchise(game.away_team)
spread_home = game.spread_line                       # + = home favored
if a.line:
    t, v = a.line.split("="); v = float(v)
    spread_home = -v if teams.franchise(t) == home else v
tot = a.total or game.total_line

# who is out: official report (Out/Doubtful) + ESPN game-day inactives when posted
inj = data.load_injuries([season]); inj = inj[inj.week == game.week]
outrows = inj[inj.report_status.isin(["Out", "Doubtful"]) | inj.gameday_inactive.fillna(False).astype(bool)]
out_names = set(outrows.full_name.map(props._key))
inactives_posted = bool(inj.gameday_inactive.any())
ids = outrows.assign(team=outrows.team.map(teams.franchise))
name_id = cur.drop_duplicates("player_id").assign(k=lambda x: x.player_display_name.map(props._key)).set_index(["k", "team"]).player_id
ids["player_id"] = ids.gsis_id.where(ids.gsis_id.notna(), [name_id.get((props._key(n), t)) for n, t in zip(ids.full_name, ids.team)])
games = pd.DataFrame({"game_id": game.game_id, "team": [home, away], "season": season, "week": game.week, "gameday": game.gameday})
vac = props.vacated_next(s[s.season >= 2015], ids.dropna(subset=["player_id"])[["team", "player_id"]].drop_duplicates(), games)

hist = props.history(s[s.season >= 2015].copy())
models = {mk: props.StatModel(mk).fit(props.StatModel(mk).rows(hist)) for mk in RUNGS}

# only players who played in one of the team's last 2 games (role is current)
recent = {}
for t in (home, away):
    wks = sorted(cur[cur.team == t].week.unique())[-2:]
    recent[t] = set(cur[(cur.team == t) & cur.week.isin(wks) & (cur.snap_pct >= 0.25)].player_id)

rows = []
for t in (home, away):
    opp = away if t == home else home
    sp = spread_home if t == home else -spread_home
    pl = nxt[(nxt.team == t) & nxt.player_id.isin(recent[t])].copy()
    pl = pl[~pl.player_display_name.map(props._key).isin(out_names)]
    pl["spread_for"], pl["pts"], pl["home"] = sp, tot / 2 + sp / 2, int(t == home)
    pl = props.with_opponent(pl, s, opp)
    pl = props._vac_pos(pl.merge(vac.drop(columns="game_id"), on="team", how="left"))
    for mk, rungs in RUNGS.items():
        q = pl[pl.position.isin(props.STATS[mk][0])]
        if q.empty:
            continue
        pred = models[mk].predict(q)
        for (_, r), pr in zip(q.iterrows(), pred):
            for rung in rungs:
                p = models[mk].p_reach(pr, rung) + FIX.get(mk, 0)
                tp = tested(mk, p)
                if tp is None or tp < a.min:
                    continue
                lab = "anytime TD" if mk == "anytime_td" else f"{rung}+ {mk.replace('_', ' ')}"
                freed = r.vac_t_pos >= 4 or r.vac_c_pos >= 4
                rows.append((t, r.player_display_name, r.position, lab, tp, price(tp), "freed-up work" if freed else ""))

print(f"{away} @ {home}  {game.gameday:%a %b %d} {game.gametime} ET   line {home} {-spread_home:+g}, total {tot:g}")
print("Out/Doubtful/inactive removed:", ", ".join(sorted(outrows[outrows.team.map(teams.franchise).isin([home, away])].full_name)) or "none")
print("ESPN game-day inactives posted:", "yes" if inactives_posted else "NO - re-run about 90 min before kickoff")
df = pd.DataFrame(rows, columns=["team", "player", "pos", "bet", "tested", "break_even", "note"])
df = df.sort_values(["player", "tested"]).groupby(["player", "bet"]).tail(1)
# for each player and market keep the HIGHEST rung that still clears --min (the most useful one)
df["market"] = df.bet.str.replace(r"^\d+\+ ", "", regex=True)
df["n"] = df.bet.str.extract(r"^(\d+)").astype(float).fillna(1)
best = df.sort_values("n").groupby(["player", "market"]).tail(1).sort_values("tested", ascending=False)
print(f"\nHighest number each player reaches with a tested chance of {a.min:.0%}+ (2023-26 hit rate of that model range).")
print("Bet only if DK's price PAYS MORE than 'break-even' (e.g. -150 pays more than -180).\n")
for x in best.itertuples():
    print(f"  {x.player:22s} {x.pos:2s} {x.team:3s}  {x.bet:24s} tested {x.tested:.0%}   break-even {x.break_even:+d}  {x.note}")
