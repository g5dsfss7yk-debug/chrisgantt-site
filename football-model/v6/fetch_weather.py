"""Game-time weather text per game from nflverse play-by-play (v6/PROTOCOL.md). python v6/fetch_weather.py 2006 2026"""
import os, sys, tempfile, urllib.request
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'v6', 'weather.csv')

def season(y):
    url = f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.parquet'
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'p.parquet')
        urllib.request.urlretrieve(url, p)
        d = pd.read_parquet(p, columns=['game_id', 'season', 'week', 'season_type', 'home_team', 'away_team', 'roof', 'weather'])
    return d.drop_duplicates('game_id')

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    old = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame()
    parts = [old[~old.season.between(a, b)]] if len(old) else []
    for y in range(a, b + 1):
        parts.append(season(y)); print(y, len(parts[-1]), flush=True)
    pd.concat(parts, ignore_index=True).sort_values('game_id').to_csv(OUT, index=False)
    print('wrote', OUT)
