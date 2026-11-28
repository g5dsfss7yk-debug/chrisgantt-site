"""One game-day run (used by the scheduled task). Run from the repo root:
  python football-model/v5/gameday.py --hours 6 --max-credits 80

1. Refresh data (current-season play-by-play + weekly player stats).
2. Odds API credits (free check). If enough: game lines (3 credits) + player props for games within --hours
   (5 credits per game), never below --reserve. If not: says so and skips paid pulls.
3. Free v3 card for this NFL week (every game, all pre-bet checks: injuries, QB, line moves, weather, teaser legs).
4. Scoreboard (grades finished picks, props included).
Everything prints; the caller summarizes it for Chris.
"""
import sys as _sys
_sys.exit('RETIRED Nov 28 2026 - Chris: "There should be no old models picking anything". Use football-model/core/ (core/HANDOFF.md).')
import argparse, os, subprocess, sys, urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # football-model/
PY = sys.executable


def sh(args, title):
    print(f'\n######## {title}', flush=True)
    r = subprocess.run([PY, '-W', 'ignore'] + args, cwd=ROOT, text=True, capture_output=True)
    print(r.stdout[-20000:], r.stderr[-3000:] if r.returncode else '', flush=True)
    return r


def refresh(season):
    sh(['v3/fetch_pbp.py', '2002', str(season)], 'play-by-play (missing seasons)')
    sh(['v3/fetch_pbp.py', str(season), str(season), '--force'], f'play-by-play {season} refresh')
    d = os.path.join(ROOT, 'data', 'v3', 'stats'); os.makedirs(d, exist_ok=True)
    for y in range(2012, season + 1):
        p = os.path.join(d, f'w_{y}.parquet')
        if y == season or not os.path.exists(p):
            urllib.request.urlretrieve(
                f'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{y}.parquet', p)
    urllib.request.urlretrieve(
        f'https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.parquet',
        os.path.join(d, f'snaps_{season}.parquet'))
    print('weekly player stats + snap counts refreshed', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours', type=float, default=6)
    ap.add_argument('--max-credits', type=int, default=80)
    ap.add_argument('--reserve', type=int, default=3)
    ap.add_argument('--week', type=int)
    o = ap.parse_args()
    now = datetime.now()
    season = now.year if now.month >= 7 else now.year - 1
    refresh(season)
    sys.path.insert(0, os.path.join(ROOT, 'v5'))
    import pricecheck
    left = pricecheck.credits_left()
    print(f'\n######## Odds API credits left: {left}')
    if left >= 3 + o.reserve:
        sh(['v5/pricecheck.py', 'nfl', '--markets', 'h2h,spreads,totals'], 'DK vs sharp: game lines (3 credits)')
        sh(['v5/pricecheck.py', 'nfl', '--props', '--hours', str(o.hours), '--max-credits', str(max(0, o.max_credits - 3)),
            '--reserve', str(o.reserve)], f'DK vs sharp: props, games within {o.hours}h')
    else:
        print('Not enough credits for paid pulls this run (they reset monthly). Free card only.')
    wk = ['--week', str(o.week)] if o.week else []
    if not o.week:   # this NFL week = the week of the next unplayed game in the nflverse schedule
        sys.path.insert(0, os.path.join(ROOT, 'v3'))
        import data
        g = data.nfl_games(refresh_hours=0)
        up = g[(g.season == season) & g.result.isna()].sort_values('gameday')
        if not up.empty:
            wk = ['--week', str(int(up.iloc[0].week))]
    if not os.path.exists(os.path.join(ROOT, 'data', 'v8', 'pricer8.pkl')):
        sh(['v8/freeze.py'], 'v8 props model: build frozen pricers (fresh container)')
    sh(['v3/card.py', 'nfl'] + wk, 'v3 card (free; all pre-bet checks)')
    sh(['v3/scoreboard.py'], 'scoreboard')


if __name__ == '__main__':
    main()
