"""v9 data (v9/PROTOCOL.md): stadium location (ESPN venue -> Open-Meteo geocoding) and hourly game-window weather
(Open-Meteo archive) for every outdoor/open game 2006-2026. python v9/fetch.py  -> data/v9/game_weather.csv"""
import os, sys, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'v3'))
import data

OUT = os.path.join(ROOT, 'data', 'v9'); os.makedirs(OUT, exist_ok=True)


def get(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception as ex:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))


def venues(o):
    p = os.path.join(OUT, 'venues.json')
    V = json.load(open(p)) if os.path.exists(p) else {}
    for st, x in o.groupby('stadium'):
        if st in V:
            continue
        loc = None
        for eid in x.espn.dropna().astype(str).tail(3):
            try:
                a = data.espn_summary('nfl', eid.split('.')[0]).get('gameInfo', {}).get('venue', {}).get('address', {})
            except Exception:
                continue
            q = a.get('zipCode') if a.get('country', 'USA') == 'USA' and a.get('zipCode') else a.get('city')
            if not q:
                continue
            r = get('https://geocoding-api.open-meteo.com/v1/search?' + urllib.parse.urlencode({'name': q, 'count': 5}))
            res = r.get('results') or []
            if a.get('state') and a.get('country', 'USA') == 'USA':
                res = [z for z in res if z.get('country_code') == 'US'] or res
            if res:
                loc = dict(lat=res[0]['latitude'], lon=res[0]['longitude'], city=a.get('city'), state=a.get('state'),
                           country=a.get('country'), query=q, matched=res[0]['name'])
                break
        V[st] = loc
        json.dump(V, open(p, 'w'), indent=1)
        print('venue', st, loc, flush=True)
    return V


def season_hours(lat, lon, start, end):
    u = ('https://archive-api.open-meteo.com/v1/archive?' + urllib.parse.urlencode(dict(
        latitude=lat, longitude=lon, start_date=start, end_date=end, hourly='precipitation,temperature_2m,wind_gusts_10m',
        temperature_unit='fahrenheit', precipitation_unit='inch', wind_speed_unit='mph', timezone='America/New_York')))
    h = get(u)['hourly']
    return pd.DataFrame({'t': pd.to_datetime(h['time']), 'rain': h['precipitation'], 'temp': h['temperature_2m'], 'gust': h['wind_gusts_10m']}).set_index('t')


if __name__ == '__main__':
    g = data.nfl_games(refresh_hours=999)
    o = g[g.roof.isin(['outdoors', 'open']) & (g.season >= 2006) & g.result.notna()].copy()
    V = venues(o)
    rows, cache = [], {}
    for (st, season), x in o.groupby(['stadium', 'season']):
        loc = V.get(st)
        if not loc:
            continue
        d0, d1 = x.gameday.min(), (pd.Timestamp(x.gameday.max()) + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        try:
            H = season_hours(loc['lat'], loc['lon'], d0, d1)
        except Exception as ex:
            print('weather failed', st, season, ex, flush=True); continue
        for _, r in x.iterrows():
            k0 = pd.Timestamp(f"{r.gameday} {r.gametime}").floor('h')
            w = H.loc[k0:k0 + pd.Timedelta(hours=3)]
            if len(w) < 4:
                continue
            rows.append(dict(game_id=r.game_id, season=r.season, stadium=st, rain=float(w.rain.sum()), temp=float(w.temp.mean()),
                             gust=float(w.gust.max())))
        time.sleep(0.3)
        print(st, season, len(x), flush=True)
    W = pd.DataFrame(rows)
    W.to_csv(os.path.join(OUT, 'game_weather.csv'), index=False)
    miss = o[~o.game_id.isin(W.game_id)]
    print(f'wrote {len(W)} games; {len(miss)} outdoor games without weather (stadium not located or fetch failed)')
