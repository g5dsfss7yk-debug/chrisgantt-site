"""Speed-up for v9/fetch.py: fills the same per-day cache (data/v9/raw) for the newest games first, 4 at a time.
fetch.py then reads the cache. Same requests, same data."""
import os, sys, json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, 'v3'))
import fetch, data

g = data.nfl_games(refresh_hours=999)
o = g[g.roof.isin(['outdoors', 'open']) & (g.season >= 2006) & g.result.notna()].sort_values('gameday', ascending=False)
V = json.load(open(os.path.join(fetch.OUT, 'venues.json')))
jobs = []
for _, r in o.iterrows():
    loc = V.get(r.stadium)
    if not loc:
        continue
    day = pd.Timestamp(r.gameday).strftime('%Y-%m-%d')
    jobs.append((loc['lat'], loc['lon'], day))
    if int(str(r.gametime)[:2]) >= 21:
        jobs.append((loc['lat'], loc['lon'], (pd.Timestamp(day) + pd.Timedelta(days=1)).strftime('%Y-%m-%d')))

def one(j):
    try:
        fetch.day_hours(*j); return 1
    except Exception as ex:
        print('fail', j, ex, flush=True); return 0

with ThreadPoolExecutor(10) as ex:
    for i, ok in enumerate(ex.map(one, jobs)):
        if i % 200 == 0:
            print(i, 'of', len(jobs), flush=True)
print('warm done')
