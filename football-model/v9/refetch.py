"""Re-fetch game-window weather for named stadiums only and replace their rows in data/v9/game_weather.csv
(v9 PROTOCOL amendment 4: Miami was located in Bordeaux, France). Same source and window as fetch.py.
python v9/refetch.py "Dolphin Stadium" "Sun Life Stadium" "Hard Rock Stadium"
A game whose weather cannot be fetched stops the run and nothing is written (no half-fixed file)."""
import os, sys, json
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, 'v3'))
import fetch, data

names = sys.argv[1:]
V = json.load(open(os.path.join(fetch.OUT, 'venues.json')))
for n in names:
    loc = V.get(n)
    assert loc and 24 <= loc['lat'] <= 50 and -125 <= loc['lon'] <= -66, f'{n} is not located in the US: {loc}'
g = data.nfl_games(refresh_hours=999)
o = g[g.roof.isin(['outdoors', 'open']) & (g.season >= 2006) & g.result.notna() & g.stadium.isin(names)].sort_values('gameday')
p = os.path.join(fetch.OUT, 'game_weather.csv')
W = pd.read_csv(p)
old = W[W.stadium.isin(names)]
rows = []
for i, (_, r) in enumerate(o.iterrows()):
    row = fetch.game_row(r, V[r.stadium])      # raises on a failed fetch -> nothing written
    if row:
        rows.append(row)
    if i % 25 == 0:
        print(i, 'of', len(o), r.gameday, flush=True)
new = pd.DataFrame(rows)
W = pd.concat([W[~W.stadium.isin(names)], new], ignore_index=True)
W = W.set_index('game_id').loc[[x for x in pd.read_csv(p).game_id if x in set(W.game_id)] +
                               [x for x in new.game_id if x not in set(pd.read_csv(p).game_id)]].reset_index()
W.to_csv(p, index=False)
print(f'replaced {len(old)} rows with {len(new)} ({len(o)} outdoor games at {", ".join(names)})')
for k in ('rain', 'temp', 'gust'):
    print(f'  {k}: mean {old[k].mean():.2f} -> {new[k].mean():.2f}, max {old[k].max():.2f} -> {new[k].max():.2f}')
