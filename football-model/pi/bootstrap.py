"""Build every data file the tools need (run once on the Pi, then the game-day job keeps them fresh).
python pi/bootstrap.py      (from football-model/)"""
import os, sys, subprocess, urllib.request
from datetime import datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); PY = sys.executable
now = datetime.now(); season = now.year if now.month >= 7 else now.year - 1


def run(args, title):
    print(f'\n== {title}', flush=True)
    r = subprocess.run([PY, '-W', 'ignore'] + args, cwd=ROOT)
    if r.returncode:
        sys.exit(f'FAILED: {title}')


run(['v3/fetch_pbp.py', '2002', str(season)], 'play-by-play 2002-now (largest download)')
d = os.path.join(ROOT, 'data', 'v3', 'stats'); os.makedirs(d, exist_ok=True)
base = 'https://github.com/nflverse/nflverse-data/releases/download'
for y in range(2012, season + 1):
    for name, url in ((f'w_{y}.parquet', f'{base}/stats_player/stats_player_week_{y}.parquet'),
                      (f'snaps_{y}.parquet', f'{base}/snap_counts/snap_counts_{y}.parquet')):
        p = os.path.join(d, name)
        if y == season or not os.path.exists(p):
            print('download', name, flush=True); urllib.request.urlretrieve(url, p)
run(['v6/fetch_weather.py', str(season), str(season)], 'game-book weather, this season (older seasons come with the repo)')
run(['v8/freeze.py'], 'v8 props model (builds its pricers)')
print('\nDone. Start the app: python pi/app.py   (or the systemd service from pi/README.md)')
