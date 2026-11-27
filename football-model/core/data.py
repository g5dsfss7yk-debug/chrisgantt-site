"""core data (core/PROTOCOL.md). Standalone - imports nothing from other model folders.
python core/data.py cfb 2014 2026      download college play-by-play, player stats and CFBD lines into data/core/cfb/"""
import os, sys, json, time, urllib.request, urllib.parse
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), 'data', 'core')
CFB = os.path.join(DATA, 'cfb')
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football'
CFBD = 'https://api.collegefootballdata.com'
PBP_URL = 'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfbfastR_cfb_pbp/play_by_play_{y}.parquet'
PS_URL = 'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/player_stats/parquet/player_stats_{y}.parquet'

PBP_COLS = ['game_id', 'season', 'week', 'season_type', 'start_date', 'neutral_site', 'venue_id', 'home', 'away',
            'home_team_division', 'away_team_division', 'pos_team', 'def_pos_team', 'play_type', 'rush', 'pass', 'sack',
            'EPA', 'success', 'yards_gained', 'turnover', 'wp_before', 'pos_team_score', 'def_pos_team_score',
            'passer_player_name', 'rusher_player_name', 'receiver_player_name', 'period',
            'home_team_pregame_elo', 'away_team_pregame_elo']
RETURN_TD = {'Interception Return Touchdown', 'Fumble Return Touchdown', 'Fumble Recovery (Opponent) Touchdown'}


def get_json(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(3 * (k + 1))


def _download(url, path):
    tmp = path + '.part'
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, path)


def fetch_cfb_pbp(y, force=False):
    out = os.path.join(CFB, f'pbp_{y}.parquet')
    if os.path.exists(out) and not force:
        return out
    raw = os.path.join(CFB, 'raw'); os.makedirs(raw, exist_ok=True)
    rp = os.path.join(raw, f'pbp_{y}.parquet')
    _download(PBP_URL.format(y=y), rp)
    import pyarrow.parquet as pq
    have = set(pq.read_schema(rp).names)
    p = pd.read_parquet(rp, columns=[c for c in PBP_COLS if c in have])
    if 'season' not in p:
        p['season'] = y
    p['return_td'] = p.play_type.isin(RETURN_TD).astype(float)
    p.to_parquet(out, index=False)
    os.remove(rp)
    return out


def fetch_cfb_players(y, force=False):
    out = os.path.join(CFB, f'players_{y}.parquet')
    if os.path.exists(out) and not force:
        return out
    raw = os.path.join(CFB, 'raw'); os.makedirs(raw, exist_ok=True)
    rp = os.path.join(raw, f'ps_{y}.parquet')
    _download(PS_URL.format(y=y), rp)
    s = pd.read_parquet(rp)
    # per player-game totals (each play row lists the players involved)
    parts = []
    for col, stat, val in (('completion_player', 'passing_yards', 'completion_yds'), ('rush_player', 'rushing_yards', 'rush_yds'),
                           ('reception_player', 'receiving_yards', 'reception_yds'), ('reception_player', 'receptions', None),
                           ('touchdown_player', 'touchdowns', None), ('target_player', 'targets', None),
                           ('completion_player', 'completions', None), ('incompletion_player', 'incompletions', None),
                           ('interception_thrown_player', 'interceptions_thrown', None), ('sack_taken_player', 'sacks_taken', None)):
        x = s[s[col].notna()][['game_id', 'team', col] + ([val] if val else [])].copy()
        x['v'] = pd.to_numeric(x[val], errors='coerce').fillna(0) if val else 1.0
        parts.append(x.groupby(['game_id', 'team', col]).v.sum().rename(stat).rename_axis(['game_id', 'team', 'player']))
    g = pd.concat(parts, axis=1).fillna(0).reset_index()
    g['season'] = y
    wk = s.drop_duplicates('game_id').set_index('game_id').week
    g['week'] = g.game_id.map(wk)
    g.to_parquet(out, index=False)
    os.remove(rp)
    return out


def fetch_cfb_lines(y, force=False):
    out = os.path.join(CFB, f'lines_{y}.csv')
    if os.path.exists(out) and not force:
        return out
    rows = []
    for st in ('regular', 'postseason'):
        d = get_json(f'{CFBD}/lines?' + urllib.parse.urlencode({'year': y, 'seasonType': st}))
        for g in d:
            for ln in g.get('lines') or []:
                rows.append(dict(game_id=g['id'], season=y, season_type=st, home=g.get('homeTeam'), away=g.get('awayTeam'),
                                 home_score=g.get('homeScore'), away_score=g.get('awayScore'), provider=ln.get('provider'),
                                 spread=ln.get('spread'), spread_open=ln.get('spreadOpen'), total=ln.get('overUnder'),
                                 total_open=ln.get('overUnderOpen'), home_ml=ln.get('homeMoneyline'), away_ml=ln.get('awayMoneyline')))
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def cfbd_cached(path, name, force=False):
    """One CFBD call, cached forever under data/core/cfb/cfbd/ (free plan: calls are scarce)."""
    d = os.path.join(CFB, 'cfbd'); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + '.json')
    if os.path.exists(p) and not force:
        return json.load(open(p))
    x = get_json(f'{CFBD}/{path}')
    json.dump(x, open(p, 'w'))
    return x


def cfb_talent(seasons):
    return pd.DataFrame([dict(season=r['year'], team=r['team'], talent=float(r['talent'])) for y in seasons
                         for r in cfbd_cached(f'talent?year={y}', f'talent_{y}')])


def cfb_returning(seasons):
    return pd.DataFrame([dict(season=r['season'], team=r['team'], returning=r.get('percentPPA')) for y in seasons
                         for r in cfbd_cached(f'player/returning?year={y}', f'returning_{y}')])


def cfb_venues():
    return pd.DataFrame([dict(venue_id=v['id'], vlat=v.get('latitude'), vlon=v.get('longitude'), dome=v.get('dome'))
                         for v in cfbd_cached('venues', 'venues')])


def cfb_team_home():
    return pd.DataFrame([dict(team=t['school'], tlat=(t.get('location') or {}).get('latitude'),
                              tlon=(t.get('location') or {}).get('longitude')) for t in cfbd_cached('teams', 'teams')])


def cfb_pbp(seasons):
    return pd.concat([pd.read_parquet(fetch_cfb_pbp(y)) for y in seasons], ignore_index=True)


def cfb_players(seasons):
    return pd.concat([pd.read_parquet(fetch_cfb_players(y)) for y in seasons], ignore_index=True)


def cfb_lines(seasons):
    return pd.concat([pd.read_csv(fetch_cfb_lines(y)) for y in seasons], ignore_index=True)


def espn(path):
    return get_json(f'{ESPN}/{path}')


if __name__ == '__main__':
    os.makedirs(CFB, exist_ok=True)
    lg, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    assert lg == 'cfb', 'NFL data comes in the NFL step'
    for y in range(a, b + 1):
        t = time.time()
        fetch_cfb_pbp(y, force=True); fetch_cfb_players(y, force=(y == b)); fetch_cfb_lines(y, force=(y == b))
        cfb_talent([y]); cfb_returning([y])
        print(y, f'{time.time() - t:.0f}s', flush=True)
    cfb_venues(); cfb_team_home()
