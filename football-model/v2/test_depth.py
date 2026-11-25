"""Nov 23 2026 (Chris: "if 2 starting WRs are out they go to the run game"). Checks, per team-game:
  - top-2 WRs by yards over the last 8 games: how many are listed Out/Doubtful that week
  - does the team then pass less (neutral-situation pass rate vs its own last-8-game average)?
  - does it score less than its implied team total, and did the line already move against it?
    PYTHONPATH=. python v2/test_depth.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from nflmodel import data, teams
from v2 import extra_data as x

seasons = range(2012, data.current_season() + 1)
st = pd.concat([x._release("stats_player", f"stats_player_week_{s}.csv", s) for s in seasons])
inj = pd.concat([x._release("injuries", f"injuries_{s}.csv", s) for s in seasons])
st["team"], inj["team"] = st.team.map(teams.franchise), inj.team.map(teams.franchise)
st["yds"] = st.rushing_yards.fillna(0).clip(lower=0) + st.receiving_yards.fillna(0).clip(lower=0)
out = inj[inj.report_status.isin(["Out", "Doubtful"])].groupby(["season", "week", "team"]).gsis_id.apply(set)
games = st[["season", "week", "team"]].drop_duplicates().sort_values(["team", "season", "week"])
games["k"] = games.groupby("team").cumcount()
st = st.merge(games, on=["season", "week", "team"])

pos = {"WR": 2, "RB": 1, "TE": 1}
rows = []
for team, gt in games.groupby("team"):
    s_t = st[st.team == team]
    for i in range(4, len(gt)):
        g = gt.iloc[i]
        recent = s_t[s_t.k.between(g.k - 8, g.k - 1)]
        o = out.get((g.season, g.week, team), set())
        r = {"season": g.season, "week": g.week, "team": team}
        for p, n in pos.items():
            top = recent[recent.position_group == p].groupby("player_id").yds.sum().nlargest(n).index
            r[f"{p}_top_out"] = sum(pid in o for pid in top)
        rows.append(r)
dep = pd.DataFrame(rows)

# outcomes: team pass rate and points
p = data.load_team_pbp(seasons)
p["team"] = p.team.map(teams.franchise)
gm = data.load_games(); gm = gm[gm.result.notna() & gm.spread_line.notna()]
gm["home_fr"], gm["away_fr"] = gm.home_team.map(teams.franchise), gm.away_team.map(teams.franchise)
n = data.load_nfelo()[["season", "week", "home_fr", "home_line_open"]]
gm = gm.merge(n, on=["season", "week", "home_fr"], how="left")
tg = pd.concat([
    gm.assign(team=gm.home_fr, pts=gm.home_score, line=-gm.spread_line, line_open=gm.home_line_open, margin=gm.result),
    gm.assign(team=gm.away_fr, pts=gm.away_score, line=gm.spread_line, line_open=-gm.home_line_open, margin=-gm.result)])
tg["implied"] = tg.total_line / 2 - tg.line / 2          # line: team's spread (- = favored)
tg = tg.merge(p[["game_id", "team", "neutral_pass"]], on=["game_id", "team"], how="left")
tg = tg.sort_values(["team", "gameday"])
tg["pass_avg8"] = tg.groupby("team").neutral_pass.transform(lambda s: s.shift(1).rolling(8, min_periods=4).mean())
tg = tg.merge(dep, on=["season", "week", "team"], how="inner")
tg["pass_drop"] = tg.neutral_pass - tg.pass_avg8
tg["vs_implied"] = tg.pts - tg.implied
tg["moved_against"] = tg.line - tg.line_open                     # + = line moved against the team
tg["ats"] = np.where(tg.margin + tg.line == 0, np.nan, (tg.margin + tg.line) > 0)

def summ(m, lab):
    q = tg[m]
    print(f"  {lab:34s} n={len(q):5d}  pass rate vs own avg {q.pass_drop.mean():+.3f}  "
          f"pts vs implied {q.vs_implied.mean():+.2f}  line moved against {q.moved_against.mean():+.2f}  "
          f"covered {q.ats.mean():.1%}")

for per, pm in (("2012-22", tg.season <= 2022), ("2023-26", tg.season >= 2023)):
    print(f"\n{per}")
    summ(pm & (tg.WR_top_out == 0) & (tg.RB_top_out == 0) & (tg.TE_top_out == 0), "no top skill player out")
    summ(pm & (tg.WR_top_out == 1), "1 of top-2 WRs out")
    summ(pm & (tg.WR_top_out == 2), "BOTH top-2 WRs out")
    summ(pm & (tg.RB_top_out == 1), "top RB out")
    summ(pm & (tg.TE_top_out == 1), "top TE out")
    summ(pm & (tg.WR_top_out + tg.RB_top_out + tg.TE_top_out >= 3), "3+ of the 4 top skill players out")
