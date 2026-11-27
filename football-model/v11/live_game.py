"""Live inputs for the ONE combined v11 game model (v11/PROTOCOL.md). Used by v3/card.py.
freeze(): fit on every completed game 2013-now -> v11/frozen.json."""
import os, sys, json, urllib.request, urllib.parse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, 'v7'))
FZ = os.path.join(HERE, 'frozen.json')
RES = os.path.join(HERE, 'results', 'v11_test.json')
GEO = os.path.join(ROOT, 'data', 'v9', 'geo_cache.json')


def freeze():
    import model
    f = model.build()
    upto = int(f[f.result.notna()].season.max())
    bs, bt, sd = model.fit_final(f, upto)
    starts = {}
    for q in pd.concat([f[f.result.notna()].h_qb, f[f.result.notna()].a_qb]).dropna():
        starts[q] = starts.get(q, 0) + 1
    json.dump(dict(fit=f'2013-{upto}', spread_x=model.SPREAD_X, total_x=model.TOTAL_X, bs=list(map(float, bs)), bt=list(map(float, bt)),
                   sd=float(sd), qb_starts=starts), open(FZ, 'w'))
    return json.load(open(FZ))


def load():
    if not os.path.exists(RES):
        return None, None
    res = json.load(open(RES))
    if not (res['replaces']['spread'] or res['replaces']['total']):
        return None, res
    fz = json.load(open(FZ)) if os.path.exists(FZ) else freeze()
    return fz, res


def wx(c, kickoff):
    """Open-Meteo hourly forecast over kickoff + 3h: (rain in, temp F, max gust mph); None indoors/unknown."""
    v = (c or {}).get('venue', {})
    if not v or v.get('indoor'):
        return None
    a = v.get('address', {}); q = a.get('zipCode') or a.get('city')
    if not q:
        return None
    geo = json.load(open(GEO)) if os.path.exists(GEO) else {}
    try:
        if q not in geo:
            r = json.load(urllib.request.urlopen('https://geocoding-api.open-meteo.com/v1/search?' + urllib.parse.urlencode({'name': q, 'count': 1}), timeout=30))
            geo[q] = [r['results'][0]['latitude'], r['results'][0]['longitude']]
            os.makedirs(os.path.dirname(GEO), exist_ok=True); json.dump(geo, open(GEO, 'w'))
        lat, lon = geo[q]
        k0 = pd.Timestamp(kickoff).tz_convert('America/New_York').floor('h').tz_localize(None)
        u = 'https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(dict(
            latitude=lat, longitude=lon, hourly='precipitation,temperature_2m,wind_gusts_10m', start_date=k0.strftime('%Y-%m-%d'),
            end_date=(k0 + pd.Timedelta(hours=4)).strftime('%Y-%m-%d'), temperature_unit='fahrenheit', precipitation_unit='inch',
            wind_speed_unit='mph', timezone='America/New_York'))
        H = pd.DataFrame(json.load(urllib.request.urlopen(u, timeout=30))['hourly']); H['time'] = pd.to_datetime(H.time)
    except Exception:
        return None
    w = H[(H.time >= k0) & (H.time <= k0 + pd.Timedelta(hours=3))]
    if w.empty:
        return None
    return float(w.precipitation.sum()), float(w.temperature_2m.mean()), float(w.wind_gusts_10m.max())


def team_inputs(card, team, qb_id, fz):
    """backup, key receiver out, lead RB out, defensive starters out, props yardage for one team (live)."""
    import live
    inj = card.injuries(team); out = live.outs(inj)
    d = card._pricer('rushing_yards')[2]
    rec, rb = live.key_players(team, d)
    ds = live.def_starters(team)
    v = dict(backup=float(fz['qb_starts'].get(qb_id, 0) < 4) if isinstance(qb_id, str) else 1.0,
             recout=float(sum(n in out for n in rec)), rbout=float(sum(n in out for n in rb)),
             dout=float(sum(n in out for n in ds.index)))
    # props yardage: listed QB's prior passing average + active RB/QB rushing averages (last game's snap list minus outs)
    s = live.snaps(); s = s[(s.team == team) & (s.offense_snaps > 0) & s.position.isin(['QB', 'RB'])]
    yds = 0.0
    qn = card.team_qb(team)
    if qn:
        x = card.next_projection('passing_yards', qn)
        yds += x[3] if x else 0.0
    if not s.empty:
        last = s[s.week == s.week.max()]
        for nm, pos in zip(last.player, last.position):
            if live.norm(nm) in out or (pos == 'QB' and qn and live.norm(nm) != live.norm(qn)):
                continue
            x = card.next_projection('rushing_yards', nm)
            yds += x[3] if x else 0.0
    v['yds'] = yds
    return v


def predict(card, x, h, a, c, kickoff, fz):
    """x = the v3 feature row (with DK spread/total). Returns (pm11, pt11, inputs text)."""
    th, ta = team_inputs(card, h, x.get('h_qb'), fz), team_inputs(card, a, x.get('a_qb'), fz)
    w = wx(c, kickoff)
    z = dict(x)
    z['gustx'] = max(w[2] - 15, 0) if w else 0.0
    z['rainx'] = min(w[0], 1.0) if w else 0.0
    z['coldx'] = max(40 - w[1], 0) if w else 0.0
    for k in ('backup', 'recout', 'rbout', 'dout', 'yds'):
        z[f'{k}_d'] = th[k] - ta[k]; z[f'{k}_s'] = th[k] + ta[k]
    xs = np.array([1.0] + [float(z[c_]) for c_ in fz['spread_x']]); xt = np.array([1.0] + [float(z[c_]) for c_ in fz['total_x']])
    pm, pt = float(xs @ np.array(fz['bs'])), float(xt @ np.array(fz['bt']))
    txt = (f"v11 inputs: weather " + (f"rain {w[0]:.2f} in / {w[1]:.0f}F / gusts {w[2]:.0f}" if w else 'none (dome or no forecast)') +
           f"; backup QB {int(ta['backup'])}/{int(th['backup'])}; key WR/TE out {int(ta['recout'])}/{int(th['recout'])}; lead RB out "
           f"{int(ta['rbout'])}/{int(th['rbout'])}; def starters out {int(ta['dout'])}/{int(th['dout'])}; props yds {ta['yds']:.0f}/{th['yds']:.0f} (away/home)")
    return pm, pt, txt
