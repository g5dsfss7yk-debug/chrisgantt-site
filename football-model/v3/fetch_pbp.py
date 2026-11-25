"""Download nflverse play-by-play (one parquet per season) and keep only the columns v3 uses."""
import os, sys, urllib.request
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'v3', 'pbp')
COLS = ['game_id', 'season', 'week', 'season_type', 'posteam', 'defteam', 'home_team', 'away_team',
        'play_type', 'down', 'epa', 'success', 'wp', 'pass', 'rush', 'qb_dropback', 'passer_player_id',
        'passer_player_name', 'qtr', 'game_seconds_remaining', 'yardline_100', 'score_differential',
        'sack', 'interception', 'fumble_lost', 'penalty', 'two_point_attempt']


def fetch(season, force=False):
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, f'pbp_{season}.parquet')
    if os.path.exists(dst) and not force:
        return dst
    url = f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet'
    tmp = dst + '.full'
    urllib.request.urlretrieve(url, tmp)
    df = pd.read_parquet(tmp)
    df[[c for c in COLS if c in df.columns]].to_parquet(dst, index=False)
    os.remove(tmp)
    return dst


if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    force = '--force' in sys.argv
    for s in range(a, b + 1):
        print(s, fetch(s, force), flush=True)
