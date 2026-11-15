"""Audit C: are ladder probabilities (X+ yards) calibrated out of sample in 2023-26?"""
import numpy as np, pandas as pd
from nflmodel import props, statprops, data, features, extra
games = features.weather(data.load_games(), data.load_game_weather(range(2009, 2027)), None)
games = games.merge(extra.build(games, data.load_team_pbp(range(2015, 2027))), on="game_id", how="left")
pg = props.load_player_games(); d = props.build(pg, games)
d = statprops.prepare(d)
LAD = {"receiving_yards": [24.5, 39.5, 49.5, 59.5, 69.5], "rushing_yards": [24.5, 39.5, 49.5, 59.5],
       "passing_yards": [174.5, 199.5, 224.5, 249.5]}
allrows = []
for mk, ladders in LAD.items():
    rows, stat = statprops._rows(d, mk); rows = rows[rows[stat].notna()]
    hist = []
    for s in range(2020, 2023):
        m = statprops._model(stat).fit(rows.loc[rows.season < s, statprops._features(stat)].fillna(0), rows.loc[rows.season < s, stat])
        cur = rows[rows.season == s]; hist.append(cur.assign(proj=m.predict(cur[statprops._features(stat)].fillna(0))))
    for s in range(2023, 2027):
        sm = statprops.StatModel(mk).fit(rows[rows.season < s], pd.concat(hist))
        test = rows[rows.season == s].copy(); test["proj"] = sm.project(test)
        for L in ladders:
            pr = [sm.p_over(p, x, L) for p, x in zip(test.position, test.proj)]
            allrows.append(pd.DataFrame({"market": mk, "season": s, "line": L, "p": pr, "hit": (test[stat] > L).values}))
        hist.append(test[rows.columns.tolist() + ["proj"]])
    print("done", mk, flush=True)
a = pd.concat(allrows).dropna()
a["bucket"] = pd.cut(a.p, [0, .5, .6, .65, .7, .75, .8, .9, 1.0])
print(a.groupby("bucket", observed=True).agg(n=("hit", "size"), predicted=("p", "mean"), actual=("hit", "mean")).round(3).to_string())
print(a[a.p >= .65].groupby("market").agg(n=("hit", "size"), predicted=("p", "mean"), actual=("hit", "mean")).round(3).to_string())
print(a[a.p >= .65].groupby("season").agg(n=("hit", "size"), predicted=("p", "mean"), actual=("hit", "mean")).round(3).to_string())
