"""v3 data layer. Every loader caches raw downloads under data/v3/ (gitignored).

Sources (all free):
  nflverse schedules  -> games.csv (lines are nflverse's closing consensus; spread_line > 0 = HOME favored)
  nflverse pbp        -> data/v3/pbp/pbp_YYYY.parquet (fetch_pbp.py)
  CollegeFootballData -> games, lines by provider (spread is the HOME number: -7 = home favored)
  ESPN JSON           -> live scoreboard/summary (DK odds, injuries, starters)
"""
import json, os, time, urllib.request, urllib.parse
import pandas as pd
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'v3')
os.makedirs(ROOT, exist_ok=True)


def _get_json(url, cache=None, max_age_h=None):
    if cache:
        p = os.path.join(ROOT, cache)
        if os.path.exists(p) and (max_age_h is None or time.time() - os.path.getmtime(p) < max_age_h * 3600):
            with open(p) as f:
                return json.load(f)
    req = urllib.request.Request(url, headers={'User-Agent': 'football-model-v3', 'Accept': 'application/json'})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            break
        except Exception:
            if i == 3:
                raise
            time.sleep(2 * (i + 1))
    if cache:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            json.dump(d, f)
    return d


# ---------------------------------------------------------------- NFL
def nfl_games(refresh_hours=6):
    p = os.path.join(ROOT, 'games.csv')
    if not os.path.exists(p) or time.time() - os.path.getmtime(p) > refresh_hours * 3600:
        urllib.request.urlretrieve('https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv', p)
    g = pd.read_csv(p)
    g['gameday'] = pd.to_datetime(g['gameday'])
    return g


def nfl_pbp(seasons):
    from fetch_pbp import fetch  # noqa
    out = []
    for s in seasons:
        out.append(pd.read_parquet(fetch(s)))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- CFB (CollegeFootballData; key added by session proxy)
CFBD = 'https://api.collegefootballdata.com'


def cfbd(path, params, cache=None, max_age_h=None):
    url = f'{CFBD}/{path}?{urllib.parse.urlencode(params)}'
    return _get_json(url, cache=cache, max_age_h=max_age_h)


def _cur_season():
    return pd.Timestamp.now().year if pd.Timestamp.now().month >= 7 else pd.Timestamp.now().year - 1


def cfb_games(year, refresh=False):
    out = []
    age = 3 if year >= _cur_season() else None
    for st in ('regular', 'postseason'):
        out += cfbd('games', {'year': year, 'seasonType': st}, cache=f'cfb/games_{year}_{st}.json',
                    max_age_h=0 if refresh else age)
    df = pd.json_normalize(out)
    return df


def cfb_lines(year, refresh=False):
    rows = []
    age = 3 if year >= _cur_season() else None
    for st in ('regular', 'postseason'):
        d = cfbd('lines', {'year': year, 'seasonType': st}, cache=f'cfb/lines_{year}_{st}.json',
                 max_age_h=0 if refresh else age)
        for g in d:
            for l in g.get('lines') or []:
                rows.append({'id': g['id'], 'season': g['season'], 'week': g['week'], 'season_type': g['seasonType'],
                             'start': g['startDate'], 'home': g['homeTeam'], 'away': g['awayTeam'],
                             'home_class': g.get('homeClassification'), 'away_class': g.get('awayClassification'),
                             'home_score': g.get('homeScore'), 'away_score': g.get('awayScore'),
                             'provider': l['provider'], 'spread': l.get('spread'), 'spread_open': l.get('spreadOpen'),
                             'total': l.get('overUnder'), 'total_open': l.get('overUnderOpen'),
                             'home_ml': l.get('homeMoneyline'), 'away_ml': l.get('awayMoneyline')})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- ESPN
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football'


def espn_scoreboard(league, dates=None, week=None, groups=None):
    lg = 'nfl' if league == 'nfl' else 'college-football'
    q = {'limit': 400}
    if dates: q['dates'] = dates
    if week: q['week'] = week
    if groups: q['groups'] = groups
    return _get_json(f'{ESPN}/{lg}/scoreboard?{urllib.parse.urlencode(q)}')


def espn_summary(league, event_id):
    lg = 'nfl' if league == 'nfl' else 'college-football'
    return _get_json(f'{ESPN}/{lg}/summary?event={event_id}')


def cfb_adv(year, refresh=False):
    """Per-team per-game advanced stats (PPA = CFBD's EPA, success rate). One row per team-game."""
    age = 3 if year >= _cur_season() else None
    rows = []
    for st in ('regular', 'postseason'):
        d = cfbd('stats/game/advanced', {'year': year, 'seasonType': st}, cache=f'cfb/adv_{year}_{st}.json',
                 max_age_h=0 if refresh else age)
        for r in d:
            o, de = r.get('offense') or {}, r.get('defense') or {}
            rows.append({'id': r['gameId'], 'season': r['season'], 'week': r['week'], 'team': r['team'],
                         'opp': r['opponent'], 'o_ppa': o.get('ppa'), 'o_sr': o.get('successRate'),
                         'o_plays': o.get('plays'), 'd_ppa': de.get('ppa'), 'd_sr': de.get('successRate'),
                         'd_plays': de.get('plays')})
    return pd.DataFrame(rows)
