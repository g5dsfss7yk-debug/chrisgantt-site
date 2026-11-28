"""v3 game-day card (FROZEN model, v3/frozen.json). Lines and prices: DraftKings via ESPN's free scoreboard.

  python v3/card.py nfl [--week N]            every NFL game this week: spread, winner, total + teaser legs
  python v3/card.py cfb [--date YYYYMMDD]     every FBS game that day
  python v3/card.py prop "Josh Allen" passing_yards 245.5 [--over -115 --under -105]
                                              fair price of the Over AND Under (and value at DK's price)
  python v3/card.py props --team BUF          fair prices for that team's players at lines near the projection

Labels: TESTED PICK = passed v3/PROTOCOL.md in both periods. LEAN = did not pass (shown with its record).
Every printed pick is written to v3/picks/log.csv (latest game-day run before kickoff wins).
"""
import sys as _sys
_sys.exit('RETIRED Nov 28 2026 - Chris: "There should be no old models picking anything". Use football-model/core/ (core/HANDOFF.md).')
import argparse, json, os, sys
from datetime import datetime, timezone
from math import erf, sqrt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data, nfl, cfb, grade, props  # noqa: E402
sys.path.insert(0, os.path.join(HERE, '..', 'v4'))
import pricegap  # noqa: E402
V4 = json.load(open(os.path.join(HERE, '..', 'v4', 'frozen.json')))
V6 = json.load(open(os.path.join(HERE, '..', 'v6', 'results', 'weather_test.json')))   # v6 weather test (v6/PROTOCOL.md)


V9F = os.path.join(HERE, '..', 'v9', 'results', 'v9_test.json')
V9 = json.load(open(V9F)) if os.path.exists(V9F) else {}


def v9_passed(prefix):
    for k, v in V9.items():
        if k.startswith(prefix + ' ') and v.get('passes'):
            return k, v
    return None, None


def v6_rec(key):
    t = V6['totals'][key]
    return f"{t['early'][0]}/{t['early'][1]} = {t['early_pct']:.1%} (2006-16) / {t['late'][0]}/{t['late'][1]} = {t['late_pct']:.1%} (2017-26)"


def v6_weather(wx):
    """Forecast -> v6 condition (amendment 2, mapped AFTER results): WINDY = gusts 25+ (the test's gust rule; ESPN
    gives no sustained wind); BAD = WINDY or rain chance 50%+. Returns 'WINDY', 'BAD' or None."""
    if not wx:
        return None
    if (wx.get('gust') or 0) >= 25:
        return 'WINDY'
    if (wx.get('precipitation') or 0) >= 50:
        return 'BAD'
    return None

FROZEN = json.load(open(os.path.join(HERE, 'frozen.json')))
LOG = os.path.join(HERE, 'picks', 'log.csv')
ESPN2NFLV = {'WSH': 'WAS', 'LAR': 'LA'}
BAD = ('Out', 'Doubtful', 'Injured Reserve', 'Suspended', 'Physically Unable to Perform')


def rec(league, key):
    r = FROZEN['records'][league][key]
    lab = 'TESTED PICK' if r['pass'] else 'LEAN'
    return lab, f"{lab} (tested {r['early']} / {r['late']})"


def rec11(kind, key):
    """v11 tested record (v11/RESULTS.md) for 'spread edge N+' / 'total edge N+'."""
    r = json.load(open(os.path.join(HERE, '..', 'v11', 'results', 'v11_test.json')))['results'][key]['v11']
    lab = 'TESTED PICK' if r['pass'] else 'LEAN'
    f = lambda z: f"{z['pct']:.1%} of {z['n']}"
    return lab, f"{lab} (v11 tested {f(r['early'])} 2014-18 / {f(r['late'])} 2019-26)"


def am(x):
    try:
        return float(str(x).replace('+', ''))
    except (TypeError, ValueError):
        return np.nan


def be(price):
    return 1 / float(grade.dec([price])[0])


def espn_odds(c):
    o = (c.get('odds') or [{}])[0]
    if 'DraftKings' not in json.dumps(o.get('provider', {})):
        return None
    ps, tt, ml = o.get('pointSpread', {}), o.get('total', {}), o.get('moneyline', {})
    g = lambda d, *k: (lambda v: v)(__import__('functools').reduce(lambda a, b: (a or {}).get(b), k, d))
    return {'home_spread': o.get('spread'), 'total': o.get('overUnder'),
            'home_spread_odds': am(g(ps, 'home', 'close', 'odds')), 'away_spread_odds': am(g(ps, 'away', 'close', 'odds')),
            'over_odds': am(g(tt, 'over', 'close', 'odds')), 'under_odds': am(g(tt, 'under', 'close', 'odds')),
            'home_ml': am(g(ml, 'home', 'close', 'odds')), 'away_ml': am(g(ml, 'away', 'close', 'odds')),
            'home_spread_open': am(g(ps, 'home', 'open', 'line')),
            'total_open': am(str(g(tt, 'over', 'open', 'line') or '').lstrip('ou'))}


def log_picks(rows):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = pd.DataFrame(rows)
    if os.path.exists(LOG):
        old = pd.read_csv(LOG, dtype={'event': str})
        # a re-run replaces ALL of that game's card rows, so a pick the new run no longer makes (e.g. a price gap
        # that closed) is not left behind (bug fix Nov 26). Props use 'espn:<id>' events and are not touched.
        old = old[~old.event.isin(set(new.event))]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(LOG, index=False)


def wp(margin, sd):
    return 0.5 * (1 + erf(margin / (sd * sqrt(2))))


def line_txt(x):
    return f'{x:+g}' if x else 'PK'


# ---------------------------------------------------------------- NFL
def nfl_card(week=None):
    q = f'&week={week}&seasontype=2' if week else ''
    sb = data._get_json(f'{data.ESPN}/nfl/scoreboard?limit=50{q}')
    g = data.nfl_games(refresh_hours=1)
    season = int(sb['leagues'][0]['season']['year']) if sb.get('leagues') else int(g.season.max())
    H, G = FROZEN['nfl']['H'], FROZEN['nfl']['G']
    games = g[g.season.between(nfl.FIRST_PBP, season)].copy()
    # starters: schedule's listed QB, checked against ESPN injuries below
    tg, qbg = nfl.team_games(range(nfl.FIRST_PBP, season + 1))
    rt = nfl.ratings(games, tg, qbg, H, G)
    f = nfl.features(games, rt)
    bs, bt, sd = nfl.fit_final(f, season)
    now = datetime.now(timezone.utc)
    rows, out = [], []
    print(f"NFL v3 card - {now:%Y-%m-%d %H:%M} UTC - DK lines/prices from ESPN. Model frozen {FROZEN['frozen_on']}.")
    print("Spreads/totals/winners have NO tested edge (LEAN). Only the teaser leg passed its test.\n")
    teaser_legs = []
    for e in sb['events']:
        c = e['competitions'][0]
        st = e['status']['type']['name']
        kick = pd.Timestamp(e['date'])
        tm = {t['homeAway']: t['team']['abbreviation'] for t in c['competitors']}
        h, a = ESPN2NFLV.get(tm['home'], tm['home']), ESPN2NFLV.get(tm['away'], tm['away'])
        od = espn_odds(c)
        hdr = f"{a} @ {h}  {kick.tz_convert('America/Chicago'):%a %b %d %I:%M %p} CT"
        if st != 'STATUS_SCHEDULED':
            print(hdr + f'  [{st} - not carded]\n'); continue
        if od is None or od['home_spread'] is None:
            print(hdr + '  [no DraftKings line on ESPN yet]\n'); continue
        r = f[(f.home_team == h) & (f.away_team == a) & (f.season == season)]
        if r.empty:
            print(hdr + '  [not in nflverse schedule]\n'); continue
        r = r.iloc[-1]
        checks = []
        try:
            summ = data.espn_summary('nfl', e['id'])
        except Exception:
            summ = {}
        inj = {}
        for t in summ.get('injuries', []):
            for i in t.get('injuries', []):
                inj[i['athlete']['displayName']] = (t['team']['abbreviation'], i['athlete'].get('position', {}).get('abbreviation'), i.get('status'))
        for side, team in (('home', h), ('away', a)):
            qn = r[f'{side}_qb_name'] if isinstance(r.get(f'{side}_qb_name'), str) else None
            if not qn:
                checks.append(f'NOT VERIFIED: no starting QB listed for {team}')
            elif qn in inj and inj[qn][2] in BAD:
                checks.append(f'NOT VERIFIED: listed QB {qn} ({team}) is {inj[qn][2]} on ESPN - QB value uses him')
            if qn and qb_starts(qn) < 4:
                checks.append(f'NOT VERIFIED - BACKUP QB: {qn} ({team}) has {qb_starts(qn)} starts in the data (needs 4). '
                              f'Spread, total and {team} passing/receiving props are NOT VERIFIED (Chris, Nov 26).')
            for n, (tab, pos, s) in inj.items():
                if pos in ('QB', 'RB', 'WR', 'TE') and s in BAD and tab == tm[side] and n != qn:
                    checks.append(f'{team} {pos} {n}: {s}')
        wx = summ.get('gameInfo', {}).get('weather')
        wline = None
        if wx and not c.get('venue', {}).get('indoor'):
            if (wx.get('gust') or 0) >= 15 or (wx.get('precipitation') or 0) >= 50:
                checks.append(f"weather (not in model): {wx.get('temperature')}F, gusts {wx.get('gust')} mph, precip {wx.get('precipitation')}%")
            lv, stxt = severe_weather(c, e['date'])
            if lv:
                checks.append(f"SEVERE WEATHER ({stxt}). Passing yds, receiving yds and receptions OVERS are NOT VERIFIED "
                              f"(v9 tested: heavy rain -> receiving yds/receptions Under, gusts 30+ -> passing yds Under; snow/freezing too few games to test).")
            elif stxt:
                checks.append(stxt)
            cond = v6_weather(wx)
            k9, v9 = v9_passed('S4')
            if 'HIGH WIND' in lv and k9:
                wtot = float(od['total'])
                up = od.get('under_odds'); up = -110.0 if up is None or np.isnan(up) else float(up)
                low = min(v9['early_pct'], v9['late_pct'])
                wlab = 'TESTED PICK' if be(up) <= low else 'NOT A BET (price)'
                wline = (f"  >> WEATHER UNDER  {wtot:g} ({up:+.0f}, needs {be(up):.1%})  {wlab} (v9 S4 gusts 30+: {v9['early'][0]}/{v9['early'][1]} = "
                         f"{v9['early_pct']:.1%} (2006-16) / {v9['late'][0]}/{v9['late'][1]} = {v9['late_pct']:.1%} (2017-26)). Forecast: {stxt}.")
                rows.append(dict(league='nfl', event=e['id'], kickoff=e['date'], game=f'{a}@{h}', market='weather_under', side='under',
                                 pick='Under', line=wtot, price=up, label=wlab, model=np.nan))
            elif cond:
                key = 'G2 WINDY' if cond == 'WINDY' else 'G3 BAD'
                if V6['totals'][key]['passes']:
                    wtot = float(od['total'])
                    up = od.get('under_odds'); up = -110.0 if up is None or np.isnan(up) else float(up)
                    wlab = 'TESTED PICK' if be(up) <= max(V6['totals'][key]['early_pct'], 0) and be(up) <= V6['totals'][key]['late_pct'] else 'NOT A BET (price)'
                    wline = (f"  >> WEATHER UNDER  {wtot:g} ({up:+.0f}, needs {be(up):.1%})  {wlab} (v6 {key}: {v6_rec(key)}). "
                             f"Tested on kickoff weather; this uses the forecast (gusts {wx.get('gust')}, rain {wx.get('precipitation')}%).")
                    rows.append(dict(league='nfl', event=e['id'], kickoff=e['date'], game=f'{a}@{h}', market='weather_under', side='under',
                                     pick='Under', line=wtot, price=up, label=wlab, model=np.nan))
                    checks.append('weather props (v6): passing and receiving yards ran BELOW projection in bad weather '
                                  '(card.py prop shows it); rushing yards did NOT run higher')
        for nm, now_, op in (('spread (home)', od['home_spread'], od.get('home_spread_open')), ('total', od['total'], od.get('total_open'))):
            if now_ is not None and op is not None and not np.isnan(op) and abs(float(now_) - op) >= 2:
                checks.append(f'CHANGE: {nm} moved {op:+g} -> {float(now_):+g} since the opener (DK via ESPN)')
        L = -float(od['home_spread'])                       # nflverse sign: + = home favored
        x = r.copy(); x['spread_line'] = L; x['total_line'] = float(od['total'])
        pm = float(nfl._pred(bs, x[nfl.SPREAD_X].values.astype(float)[None, :])[0])
        pt = float(nfl._pred(bt, x[nfl.TOTAL_X].values.astype(float)[None, :])[0])
        v11txt = None
        try:
            sys.path.insert(0, os.path.join(HERE, '..', 'v11')); import live_game as v11g
            fz11, res11 = v11g.load()
            if fz11:
                pm11, pt11, v11txt = v11g.predict(sys.modules[__name__], x, h, a, c, e['date'], fz11)
                v3m, v3t = pm, pt
                if res11['replaces']['spread']:
                    pm, sd = pm11, fz11['sd']
                if res11['replaces']['total']:
                    pt = pt11
        except Exception as ex:
            v11txt = f'v11 not available ({ex.__class__.__name__}: {ex}) - v3 numbers shown'
        edge = pm - L
        side_home = edge > 0
        sp_team, sp_line = (h, -L) if side_home else (a, L)
        sp_price = od['home_spread_odds'] if side_home else od['away_spread_odds']
        key = 'spread edge 2+' if abs(edge) >= 2 else 'spread edge 1+' if abs(edge) >= 1 else 'spread edge 0+'
        lab, rtxt = rec('nfl', key)
        if v11txt and not v11txt.startswith('v11 not'):
            lab, rtxt = rec11('spread', key)
        ph = wp(pm, sd)
        w_team, w_p, w_price = (h, ph, od['home_ml']) if ph >= 0.5 else (a, 1 - ph, od['away_ml'])
        ev = w_p * float(grade.dec([w_price])[0]) - 1 if not np.isnan(w_price) else np.nan
        tedge = pt - x.total_line
        t_side = 'Over' if tedge > 0 else 'Under'
        t_price = od['over_odds'] if tedge > 0 else od['under_odds']
        tkey = 'total edge 2+' if abs(tedge) >= 2 else 'total edge 1+' if abs(tedge) >= 1 else 'total edge 0+'
        tlab, ttxt = rec('nfl', tkey)
        if v11txt and not v11txt.startswith('v11 not'):
            tlab, ttxt = rec11('total', tkey)
        mlab, mtxt = rec('nfl', 'moneyline EV 3%+')
        print(hdr)
        print(f"  QBs (schedule): {r.get('away_qb_name')} / {r.get('home_qb_name')}")
        print(f"  SPREAD  {sp_team} {line_txt(sp_line)} ({sp_price:+.0f}, needs {be(sp_price):.1%})  model: {h if pm >= 0 else a} by {abs(pm):.1f}, edge {abs(edge):.1f}  {rtxt}")
        print(f"  WINNER  {w_team} ({w_price:+.0f}) model chance {w_p:.0%}, value at DK price {ev:+.0%}  "
              f"{'LEAN - moneyline rule (3%+ value) ' + mtxt.split(' ', 1)[1] if ev >= 0.03 else 'LEAN (under 3% value)'}")
        print(f"  TOTAL   {t_side} {x.total_line:g} ({t_price:+.0f}, needs {be(t_price):.1%})  model {pt:.1f}  {ttxt}")
        if v11txt:
            print(f"  {v11txt}" + (f"  [v3 had {h if v3m >= 0 else a} by {abs(v3m):.1f}, total {v3t:.1f}]" if not v11txt.startswith('v11 not') else ''))
        for dside, dteam, dline in (('home', h, -L), ('away', a, L)):
            if 1.5 <= dline <= 2.5:
                key2 = 'teaser leg dog +1.5..+2.5, total<=44*' if x.total_line <= 44 else 'teaser leg dog +1.5..+2.5'
                tl, tt = rec('nfl', key2)
                print(f"  >> TEASER LEG  {dteam} {dline:+g} -> {dline + 6:+g}  {tt}. Needs 73.9%/leg at -120 for 2 teams; "
                      f"DK's teaser price is NOT checked by any tool - read it on the slip.")
                teaser_legs.append(f'{dteam} {dline + 6:+g}')
                rows.append(dict(league='nfl', event=e['id'], kickoff=e['date'], game=f'{a}@{h}', market='teaser_leg', side=dside,
                                 pick=dteam, line=dline + 6, price=np.nan, label=tl, model=np.nan))
        imp, gp = pricegap.gap('nfl', od['home_ml'], od['away_ml'], L)
        if gp is not None and abs(gp) >= 1:
            gs, gteam, gline = ('home', h, -L) if gp > 0 else ('away', a, L)
            gprice = od['home_spread_odds'] if gp > 0 else od['away_spread_odds']
            v = V4['nfl_price_gap']
            print(f"  >> PRICE GAP  {gteam} {line_txt(gline)} ({gprice:+.0f}): DK moneyline implies {h} by {imp:+.1f}, spread says {L:+.1f}. "
                  f"TESTED PICK (v4: {v['early']} / {v['late']}; not proven above break-even - {v['note'].split('; ', 1)[1]})")
            glab = 'TESTED PICK'
            if be(gprice) > 0.539:
                print(f"     !! at {gprice:+.0f} DK needs {be(gprice):.1%} - above the rule's 53.9% record: NOT a bet at this price")
                glab = 'NOT A BET (price)'   # logged apart so it never counts in the TESTED PICK record (bug fix Nov 26)
            rows.append(dict(league='nfl', event=e['id'], kickoff=e['date'], game=f'{a}@{h}', market='price_gap', side=gs,
                             pick=gteam, line=gline, price=gprice, label=glab, model=round(imp, 2)))
        if wline:
            print(wline)
        for ch in checks:
            print(f'  ** {ch}')
        print()
        base = dict(league='nfl', event=e['id'], kickoff=e['date'], game=f'{a}@{h}')
        rows += [dict(base, market='spread', side='home' if side_home else 'away', pick=sp_team, line=sp_line, price=sp_price, label=lab, model=round(pm, 2)),
                 dict(base, market='winner', side='home' if ph >= 0.5 else 'away', pick=w_team, line=np.nan, price=w_price, label=mlab if ev >= 0.03 else 'LEAN', model=round(w_p, 3)),
                 dict(base, market='total', side=t_side.lower(), pick=t_side, line=x.total_line, price=t_price, label=tlab, model=round(pt, 2))]
    gaps = [f"{r_['pick']} {line_txt(r_['line'])}" for r_ in rows if r_['market'] == 'price_gap' and r_['label'] == 'TESTED PICK']
    print('TESTED PRICE GAP picks (v4):', ', '.join(gaps) if gaps else 'none')
    if teaser_legs:
        print('TESTED TEASER LEGS this card:', ', '.join(teaser_legs))
    else:
        print('No dog +1.5..+2.5 on this card -> no tested teaser leg.')
    if rows:
        for r_ in rows:
            r_['logged_at'] = now.isoformat(timespec='seconds')
        log_picks(rows)


# ---------------------------------------------------------------- CFB
def cfb_card(date=None):
    date = date or datetime.now().strftime('%Y%m%d')
    sb = data._get_json(f'{data.ESPN}/college-football/scoreboard?dates={date}&groups=80&limit=400')
    season = int(sb['leagues'][0]['season']['year'])
    H, G = FROZEN['cfb']['H'], FROZEN['cfb']['G']
    for y in (season,):
        data.cfb_games(y, refresh=True); data.cfb_lines(y, refresh=True); data.cfb_adv(y, refresh=True)
    g, a = cfb.load(range(cfb.FIRST, season + 1))
    f = cfb.features(g, a, H, G, range(2013, season + 1))
    bs, bt, sd = cfb.fit_final(f, season)
    now = datetime.now(timezone.utc)
    print(f"CFB v3 card {date} - DK lines from ESPN. Model frozen {FROZEN['frozen_on']}. No college bet type passed its test: all LEAN.\n")
    rows = []
    for e in sb['events']:
        c = e['competitions'][0]
        st = e['status']['type']['name']
        tm = {t['homeAway']: t['team']['location'] for t in c['competitors']}
        hdr = f"{tm['away']} @ {tm['home']}  {pd.Timestamp(e['date']).tz_convert('America/Chicago'):%a %I:%M %p} CT"
        if st != 'STATUS_SCHEDULED':
            continue
        od = espn_odds(c)
        r = f[f.id == int(e['id'])]
        if od is None or od['home_spread'] is None or r.empty:
            print(hdr + '  [no DK line on ESPN or game not in CFBD]\n'); continue
        r = r.iloc[0].copy()
        hs = float(od['home_spread'])
        r['line'] = -hs
        r['total_used'] = float(od['total']) if od['total'] is not None else np.nan
        pm = float(cfb._pred(bs, r[cfb.SPREAD_X].values.astype(float)[None, :])[0])
        edge = pm - r.line
        home = edge > 0
        sp_team, sp_line, sp_price = (r.homeTeam, hs, od['home_spread_odds']) if home else (r.awayTeam, -hs, od['away_spread_odds'])
        key = 'spread edge 4+' if abs(edge) >= 4 else 'spread edge 2+' if abs(edge) >= 2 else 'spread edge 0+'
        lab, rtxt = rec('cfb', key)
        ph = wp(pm, sd)
        w_team, w_p, w_price = (r.homeTeam, ph, od['home_ml']) if ph >= 0.5 else (r.awayTeam, 1 - ph, od['away_ml'])
        print(hdr)
        print(f"  SPREAD  {sp_team} {line_txt(sp_line)} ({sp_price:+.0f})  model: {r.homeTeam if pm >= 0 else r.awayTeam} by {abs(pm):.1f}, edge {abs(edge):.1f}  {rtxt}")
        print(f"  WINNER  {w_team} ({w_price:+.0f}) model chance {w_p:.0%}  LEAN (not tested)")
        base = dict(league='cfb', event=e['id'], kickoff=e['date'], game=f"{tm['away']}@{tm['home']}")
        rows += [dict(base, market='spread', side='home' if home else 'away', pick=sp_team, line=sp_line, price=sp_price, label=lab, model=round(pm, 2)),
                 dict(base, market='winner', side='home' if ph >= 0.5 else 'away', pick=w_team, line=np.nan, price=w_price, label='LEAN', model=round(w_p, 3))]
        if not np.isnan(r.total_used):
            pt = float(cfb._pred(bt, r[cfb.TOTAL_X].values.astype(float)[None, :])[0])
            ts = 'Over' if pt > r.total_used else 'Under'
            tp = od['over_odds'] if ts == 'Over' else od['under_odds']
            tkey = 'total edge 4+' if abs(pt - r.total_used) >= 4 else 'total edge 2+' if abs(pt - r.total_used) >= 2 else 'total edge 0+'
            tlab, ttxt = rec('cfb', tkey)
            print(f"  TOTAL   {ts} {r.total_used:g} ({tp:+.0f})  model {pt:.1f}  {ttxt}")
            rows.append(dict(base, market='total', side=ts.lower(), pick=ts, line=r.total_used, price=tp, label=tlab, model=round(pt, 2)))
        imp, gp = pricegap.gap('cfb', od['home_ml'], od['away_ml'], r.line)
        if gp is not None and abs(gp) >= 1:
            gt, gl = (r.homeTeam, hs) if gp > 0 else (r.awayTeam, -hs)
            v = V4['cfb_price_gap']
            print(f"  PRICE GAP  {gt} {line_txt(gl)}: DK moneyline implies {r.homeTeam} by {imp:+.1f}, spread says {r.line:+.1f}. "
                  f"LEAN (v4: {v['early']} / {v['late']}; failed EARLY by 0.2 pts)")
            rows.append(dict(base, market='price_gap', side='home' if gp > 0 else 'away', pick=gt, line=gl,
                             price=od['home_spread_odds'] if gp > 0 else od['away_spread_odds'], label='LEAN', model=round(imp, 2)))
        if not np.isnan(r.get('oth_spread', np.nan)) and abs(hs - r.oth_spread) >= 1:
            gt = r.homeTeam if hs > r.oth_spread else r.awayTeam
            _, gtxt = rec('cfb', 'DK gap 1+ vs other books')
            print(f"  DK GAP  DK {r.homeTeam} {line_txt(hs)} vs other books {line_txt(r.oth_spread)} -> {gt} gets the better number at DK. "
                  f"{gtxt} (2023-24 good, 2025-26 under 50%; capture times unknown)")
        print()
    for r_ in rows:
        r_['logged_at'] = now.isoformat(timespec='seconds')
    if rows:
        log_picks(rows)


# ---------------------------------------------------------------- props
_P = {}


def _pricer(stat):
    if stat not in _P:
        d = props.weekly()
        s = props.project(d, stat)
        _P[stat] = (s, props.Pricer(s, stat), d)
    return _P[stat]


def next_projection(stat, player):
    """Projection for the player's NEXT game, from all games so far (same formula as the backtest)."""
    s, pr, d = _pricer(stat)
    pos_, filt = props.STATS[stat]
    m = d[(d.player_display_name.str.lower() == player.lower())]
    if m.empty:
        return None
    pid = m.player_id.iloc[-1]
    hist = s[s.player_id == pid]
    if len(hist) < 3:
        return None
    a = 0.5 ** (1 / props.HL)
    v = hist._v.values
    w = a ** np.arange(len(v))[::-1]
    avg = (w * v).sum() / w.sum()
    return pid, hist.position.iloc[-1], hist.team.iloc[-1], avg, pr


def opp_factor(stat, team, pos):
    """Next opponent (nflverse schedule) and its weighted allowed-vs-league factor for this position."""
    s, pr, d = _pricer(stat)
    g = data.nfl_games()
    up = g[g.result.isna() & ((g.home_team == team) | (g.away_team == team))].sort_values('gameday')
    if up.empty:
        return None, 1.0
    r = up.iloc[0]
    opp = r.away_team if r.home_team == team else r.home_team
    dg = s[s.position == pos].groupby(['opponent_team', 'order'])._v.sum().reset_index()
    a = 0.5 ** (1 / props.HL)
    def ew(v):
        w = a ** np.arange(len(v))[::-1]
        return (w * v).sum() / w.sum()
    allowed = dg.groupby('opponent_team')._v.apply(lambda v: ew(v.values))
    if opp not in allowed.index:
        return opp, 1.0
    return opp, float(allowed[opp] / allowed.mean())


NFLV2ESPN = {'WAS': 'WSH', 'LA': 'LAR'}
_INJ = {}


def injuries(team):
    """ESPN injury list for the team's next game: {player name: status}. Empty dict if ESPN has none."""
    if team in _INJ:
        return _INJ[team]
    g = data.nfl_games()
    up = g[g.result.isna() & ((g.home_team == team) | (g.away_team == team))].sort_values('gameday')
    out = {}
    if not up.empty:
        day = pd.Timestamp(up.iloc[0].gameday).strftime('%Y%m%d')
        sb = data._get_json(f'{data.ESPN}/nfl/scoreboard?dates={day}&limit=50')
        ab = NFLV2ESPN.get(team, team)
        for e in sb.get('events', []):
            if ab in [t['team']['abbreviation'] for t in e['competitions'][0]['competitors']]:
                s = data.espn_summary('nfl', e['id'])
                for t in s.get('injuries', []):
                    if t['team']['abbreviation'] == ab:
                        out = {i['athlete']['displayName']: i.get('status') for i in t['injuries']}
    _INJ[team] = out
    return out


def next_game(team):
    """(ESPN event, competition, team is home) for the team's next game, or (None, None, None)."""
    g = data.nfl_games()
    up = g[g.result.isna() & ((g.home_team == team) | (g.away_team == team))].sort_values('gameday')
    if up.empty:
        return None, None, None
    day = pd.Timestamp(up.iloc[0].gameday).strftime('%Y%m%d')
    sb = data._get_json(f'{data.ESPN}/nfl/scoreboard?dates={day}&limit=50')
    ab = NFLV2ESPN.get(team, team)
    for e in sb.get('events', []):
        c = e['competitions'][0]
        for t in c['competitors']:
            if t['team']['abbreviation'] == ab:
                return e, c, t.get('homeAway') == 'home'
    return None, None, None


def v7_notes(player, stat, pos, team):
    """v7 tested flags (v7/RESULTS.md) for this prop. The v3 chances are NOT changed (frozen); these are notes."""
    sys.path.insert(0, os.path.join(HERE, '..', 'v7'))
    import live
    notes = []
    e, c, home = next_game(team)
    od = espn_odds(c) if c else None
    if od and od.get('home_spread') is not None and od.get('total') is not None:
        fav = -float(od['home_spread']) if home else float(od['home_spread'])     # + = this team favored
        itt = (float(od['total']) + fav) / 2
        for key, cond, side in (('A1', stat == 'passing_yards' and itt >= 26.5, 'OVER'), ('A2', stat == 'passing_yards' and itt <= 19.5, 'UNDER'),
                                ('A6', stat == 'receiving_yards' and itt <= 19.5, 'UNDER')):
            k, v = live.passed(key)
            if cond and k:
                notes.append(f"v7 {key} (DK team total {itt:.1f}): {stat.replace('_', ' ')} went {side} the projection "
                             f"{live.rec_txt(v)} - lean {side}")
    out = live.outs(injuries(team))
    if out and stat in ('receiving_yards', 'receptions', 'rushing_yards'):
        rec, rb = live.key_players(team, _pricer(stat)[2])
        me = live.norm(player)
        gone_rec = [rec[n] for n in rec if n in out and n != me]
        gone_rb = [rb[n] for n in rb if n in out and n != me]
        if pos in ('WR', 'TE') and gone_rec and stat in ('receiving_yards', 'receptions'):
            k, v = live.passed('B1' if stat == 'receiving_yards' else 'B2')
            if k:
                notes.append(f"v7 {k.split()[0]} (key receiver out: {', '.join(gone_rec)}): teammates went OVER the projection {live.rec_txt(v)} - lean OVER")
        if pos == 'RB' and gone_rb and stat == 'rushing_yards':
            k, v = live.passed('B3')
            if k:
                notes.append(f"v7 B3 (key RB out: {', '.join(gone_rb)}): other RBs went OVER the projection {live.rec_txt(v)} - lean OVER")
    return notes


GEO = os.path.join(HERE, '..', 'data', 'v9', 'geo_cache.json')
SEV_STATS = ('passing_yards', 'receiving_yards', 'receptions')


def severe_weather(c, kickoff_iso):
    """Untested flags (Chris, Nov 26 - v9 severity test pending): Open-Meteo hourly FORECAST for the stadium over
    kickoff + 3 hours. Returns (list of levels, text). Levels: HEAVY RAIN (rain 0.30+ in), SNOW (snow 0.5+ in, or
    0.10+ in precipitation at 32F or below), HIGH WIND (gusts 30+ mph), FREEZING WET (0.10+ in at 36F or below)."""
    import urllib.request, urllib.parse
    v = (c or {}).get('venue', {})
    if not v or v.get('indoor'):
        return [], ''
    a = v.get('address', {})
    q = a.get('zipCode') or a.get('city')
    if not q:
        return [], ''
    geo = json.load(open(GEO)) if os.path.exists(GEO) else {}
    try:
        if q not in geo:
            # count 5 + prefer a US match for a US stadium, as v9/fetch.py does (bug fix Nov 27: 'Santa Clara' with
            # count 1 returned Santa Clara, Cuba for Levi's Stadium)
            r = json.load(urllib.request.urlopen('https://geocoding-api.open-meteo.com/v1/search?' + urllib.parse.urlencode({'name': q, 'count': 5}), timeout=30))
            res = r.get('results') or []
            if a.get('country', 'USA') == 'USA':
                res = [z for z in res if z.get('country_code') == 'US'] or res
            geo[q] = [res[0]['latitude'], res[0]['longitude']]
            os.makedirs(os.path.dirname(GEO), exist_ok=True); json.dump(geo, open(GEO, 'w'))
        lat, lon = geo[q]
        k0 = pd.Timestamp(kickoff_iso).tz_convert('America/New_York').floor('h').tz_localize(None)
        u = 'https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(dict(
            latitude=lat, longitude=lon, hourly='precipitation,snowfall,temperature_2m,wind_gusts_10m', start_date=k0.strftime('%Y-%m-%d'),
            end_date=(k0 + pd.Timedelta(hours=4)).strftime('%Y-%m-%d'), temperature_unit='fahrenheit', precipitation_unit='inch',
            wind_speed_unit='mph', timezone='America/New_York'))
        h = json.load(urllib.request.urlopen(u, timeout=30))['hourly']
    except Exception as ex:
        return [], f'severe-weather forecast not available ({ex.__class__.__name__}) - check it by hand'
    H = pd.DataFrame(h); H['time'] = pd.to_datetime(H.time)
    w = H[(H.time >= k0) & (H.time <= k0 + pd.Timedelta(hours=3))]
    if w.empty:
        return [], ''
    rain, snow, temp, gust = w.precipitation.sum(), w.snowfall.sum(), w.temperature_2m.mean(), w.wind_gusts_10m.max()
    lv = []
    if rain >= 0.30: lv.append('HEAVY RAIN')
    if snow >= 0.5 or (rain >= 0.10 and temp <= 32): lv.append('SNOW')
    if gust >= 30: lv.append('HIGH WIND')
    if rain >= 0.10 and temp <= 36: lv.append('FREEZING WET')
    txt = (f"{', '.join(lv)}: forecast kickoff+3h rain {rain:.2f} in, snow {snow:.1f} in, {temp:.0f}F, gusts {gust:.0f} mph (Open-Meteo)"
           if lv else '')
    return lv, txt


def qb_starts(name):
    """Games with 15+ pass attempts for this QB in nflverse weekly stats (2012-now) - 'starts' for the backup-QB check."""
    d = _pricer('passing_yards')[2]
    return int(((d.player_display_name == name) & (d.attempts >= 15)).sum())


def team_qb(team):
    """Listed starting QB for the team's next game (nflverse schedule)."""
    g = data.nfl_games()
    up = g[g.result.isna() & ((g.home_team == team) | (g.away_team == team))].sort_values('gameday')
    if up.empty:
        return None
    r = up.iloc[0]
    q = r.home_qb_name if r.home_team == team else r.away_qb_name
    return q if isinstance(q, str) else None


def weather_for(team):
    """ESPN forecast for the team's next game (None if indoor or none listed)."""
    g = data.nfl_games()
    up = g[g.result.isna() & ((g.home_team == team) | (g.away_team == team))].sort_values('gameday')
    if up.empty:
        return None
    day = pd.Timestamp(up.iloc[0].gameday).strftime('%Y%m%d')
    sb = data._get_json(f'{data.ESPN}/nfl/scoreboard?dates={day}&limit=50')
    ab = NFLV2ESPN.get(team, team)
    for e in sb.get('events', []):
        c = e['competitions'][0]
        if ab in [t['team']['abbreviation'] for t in c['competitors']]:
            if c.get('venue', {}).get('indoor'):
                return None
            return data.espn_summary('nfl', e['id']).get('gameInfo', {}).get('weather')
    return None


V6_PROP = {'passing_yards': 'P1', 'receiving_yards': 'P3', 'rushing_yards': 'P2'}


def role_check(stat, player):
    """ROLE CHECK (Chris's earlier rule, restored Nov 26): the projection weights past seasons, so a role change
    is invisible to it. Flag when the projection is more than 1.5x (or under 0.67x) BOTH this season's per-game
    average and the last-3-games average. Returns (season_avg, last3_avg, flagged)."""
    s, pr, d = _pricer(stat)
    m = d[d.player_display_name.str.lower() == player.lower()]
    if m.empty:
        return None, None, True
    # every game he played this season (nflverse weekly rows), NOT only games where he was targeted/carried -
    # the projection rows skip zero-target games, which inflates fringe players (bug found Nov 26)
    src = 'td_count' if stat == 'anytime_td' else stat
    allg = d[(d.player_id == m.player_id.iloc[-1]) & (d.season == d.season.max())]
    # nflverse weekly rows exist only when a player records a stat; snap counts list every game he was on the field.
    # Games with offensive snaps but no stats row count as 0 (Nov 26 fix: backups' empty games were invisible).
    sp = os.path.join(props.ROOT, 'stats', f'snaps_{int(d.season.max())}.parquet')
    if os.path.exists(sp):
        sn = pd.read_parquet(sp)
        wk = sn[(sn.player.str.lower() == player.lower()) & (sn.offense_snaps > 0)].week.unique()
        missing = sorted(set(wk) - set(allg.week))
        if missing:
            z = pd.DataFrame({'week': missing})
            for col in ('targets', 'carries', 'attempts', 'receptions', 'receiving_yards', 'rushing_yards',
                        'passing_yards', 'td_count'):
                z[col] = 0.0
            allg = pd.concat([allg, z], ignore_index=True).sort_values('week')
    if len(allg) < 3:
        return None, None, True
    x = next_projection(stat, player)
    if x is None:
        return None, None, True
    proj = x[3] * opp_factor(stat, x[2], x[1])[1]
    sa, l3 = float(allg[src].fillna(0).mean()), float(allg[src].fillna(0).tail(3).mean())
    hi, lo = max(sa, l3), min(sa, l3)
    flagged = (hi <= 0 and proj > 0) or proj > 1.5 * hi or (lo > 0 and proj < 0.67 * lo)
    # chances come from games where he got a look; if he often gets none, they are overstated
    opp = {'receiving_yards': allg.targets, 'receptions': allg.targets, 'rushing_yards': allg.carries,
           'passing_yards': allg.attempts, 'anytime_td': allg.targets.fillna(0) + allg.carries.fillna(0)}[stat]
    if (opp.fillna(0) == 0).mean() > 0.25:
        flagged = True
    return sa, l3, bool(flagged)


def price_prop(player, stat, line, over=None, under=None):
    x = next_projection(stat, player)
    if x is None:
        print(f'{player} {stat}: fewer than 3 qualifying games in nflverse weekly stats - I don\'t know.'); return
    pid, pos, team, avg, pr = x
    st = injuries(team).get(player)
    if st in BAD:
        print(f"{player} ({team}) is {st} on ESPN's injury list - NO PRICE (failed check)."); return
    if st:
        print(f"** {player} is {st} on ESPN's injury list - NOT VERIFIED until inactives post (~90 min before kickoff).")
    d_ = _pricer(stat)[2]   # skill players only (bug fix Nov 26: defenders/backup QBs were listed as teammates out)
    skill = set(d_[d_.position.isin(['RB', 'WR', 'TE', 'FB'])].player_display_name)
    mates = [n for n, s_ in injuries(team).items() if s_ in BAD and n != player and n in skill]
    if mates and stat != 'passing_yards':
        print(f"** TEAMMATES OUT ({', '.join(mates)}): their targets/carries are NOT moved to {player} - projection may be low. NOT VERIFIED.")
    opp, opp_f = opp_factor(stat, team, pos)
    proj = avg * opp_f
    wx = weather_for(team)
    v8 = v8_chance(player, stat, pos, team, proj, line, wx)
    if v8 is None and v6_weather(wx) and stat in V6_PROP:
        t = V6['props'][V6_PROP[stat]]
        e_, l_ = t['early']['bad'], t['late']['bad']
        if t['passes']:
            print(f"** WEATHER (v6 {V6_PROP[stat]}, forecast gusts {wx.get('gust')} / rain {wx.get('precipitation')}%): in bad weather {stat.replace('_', ' ')} "
                  f"went {t['side'].upper()} the projection {e_['actual']:.0%} (2019-22) / {l_['actual']:.0%} (2023-26) vs model "
                  f"{e_['predicted']:.0%} / {l_['predicted']:.0%}. The chances below do NOT include weather - lean {t['side'].upper()}.")
        else:
            print(f"** WEATHER: forecast gusts {wx.get('gust')} / rain {wx.get('precipitation')}%. v6 test found NO weather effect on {stat.replace('_', ' ')} "
                  f"vs the projection ({t['gap_early']*100:+.1f} / {t['gap_late']*100:+.1f} pts).")
    for n_ in (v7_notes(player, stat, pos, team) if v8 is None else []):
        print(f"** {n_}. The chances below do NOT include this.")
    e_, c_, _ = next_game(team)
    sev, stxt = severe_weather(c_, e_['date']) if e_ else ([], '')
    if stat in SEV_STATS and (sev or v6_weather(wx)):
        why = f"SEVERE WEATHER ({stxt})" if sev else f"bad weather (gusts {wx.get('gust')} / rain {wx.get('precipitation')}%)"
        print(f"** {why}: OVER on {stat.replace('_', ' ')} is NOT VERIFIED (Chris, Nov 26: teams stop throwing in this weather). Under is not flagged.")
        for key, lev, st_ in (('S6', 'HEAVY RAIN', 'receiving_yards'), ('S7', 'HEAVY RAIN', 'receptions'), ('S11', 'HIGH WIND', 'passing_yards')):
            k9, v9 = v9_passed(key)
            if k9 and lev in sev and stat == st_:
                print(f"** v9 {key} TESTED ({lev}): {stat.replace('_', ' ')} went UNDER the projection {v9['early']['actual']:.0%} vs model "
                      f"{v9['early']['predicted']:.0%} (2019-22) / {v9['late']['actual']:.0%} vs {v9['late']['predicted']:.0%} (2023-26) - lean UNDER.")
    elif stxt:
        print(f"** {stxt}")
    tq = team_qb(team)
    if stat in ('passing_yards', 'receiving_yards', 'receptions') and tq and qb_starts(tq) < 4:
        print(f"** BACKUP QB: {tq} ({team}) has {qb_starts(tq)} starts in the data (needs 4) - NOT VERIFIED.")
    if e_:
        left = (pd.Timestamp(e_['date']) - pd.Timestamp.now(tz='UTC')).total_seconds() / 3600
        if left > 2:
            print(f"** PRICE CHECK: kickoff in {left:.1f} h - re-check this DK price and inactives within 2 h of kickoff.")
    sa, l3, rf = role_check(stat, player)
    if rf:
        print(f"** ROLE CHECK: {player} this season {sa if sa is None else round(sa, 1)}/game, last 3 {l3 if l3 is None else round(l3, 1)} - "
              f"far from the projection. NOT VERIFIED (role changed or too few games).")
    p3 = p = pr.p_over(pos, proj, line)
    cal = FROZEN['props'][stat]
    note = 'calibrated 2023-26' if cal['pass'] else f"NOT calibrated (worst gap {cal['worst_gap']:.1%} in 2023-26)"
    if v8 is not None:
        p, proj8, desc, fz = v8
        note8 = 'calibrated 2023-26' if fz['calibrated'] else f"NOT calibrated (worst gap {fz['worst_gap']:.1%} in 2023-26)"
        print(f"{player} ({team} {pos} vs {opp}) {stat} {line}: v8 projection {proj8:.1f} ({desc}); Over {p:.1%} (fair {props.fair_american(p)}), "
              f"Under {1 - p:.1%} (fair {props.fair_american(1 - p)}). {note8}. [v3 was {proj:.1f}, Over {p3:.1%}] LEAN: beating DK prices is not tested.")
    else:
        print(f"{player} ({team} {pos} vs {opp}, opponent factor {opp_f:.2f}) {stat} {line}: projection {proj:.1f}; Over {p:.1%} (fair {props.fair_american(p)}), "
              f"Under {1 - p:.1%} (fair {props.fair_american(1 - p)}). {note}. LEAN: beating DK prices is not tested.")
    LJ = os.path.join(HERE, '..', 'v10', 'learned.json')
    if over is not None and os.path.exists(LJ):
        lj = json.load(open(LJ))
        if lj.get('coef'):
            a_, b_, c_ = lj['coef']; lgt = lambda q: np.log(min(max(q, 1e-3), 1 - 1e-3) / (1 - min(max(q, 1e-3), 1 - 1e-3)))
            pl = 1 / (1 + np.exp(-(a_ + b_ * lgt(p) + c_ * lgt(be(over)))))
            print(f"   v10 learned Over chance {pl:.1%} (from {lj['n']} graded DK prices: weight on model {b_:.2f}, on DK {c_:.2f}) - "
                  f"{'PROVEN' if lj.get('proven') else 'NOT yet proven, information only'}")
    too_good = False
    for side, price, q in (('Over', over, p), ('Under', under, 1 - p)):
        if price is not None:
            ev = q * float(grade.dec([price])[0]) - 1
            print(f"   DK {side} {price:+.0f}: needs {be(price):.1%}, model {q:.1%} -> value {ev:+.1%}")
            if q - be(price) > 0.15:
                too_good = True
                print(f"   ** TOO GOOD TO BE TRUE: model is {100 * (q - be(price)):.0f} pts above DK's price - DK likely knows something the "
                      f"model does not. NOT VERIFIED (Chris, Nov 26).")
    if over is not None or under is not None:
        flags = [f for f, on in (('questionable', bool(st)), ('teammates_out', bool(mates) and stat != 'passing_yards'),
                                 ('role_check', bool(rf)), ('weather', bool(v6_weather(wx))), ('severe', bool(sev)), ('too_good', too_good),
                                 ('backup_qb', bool(tq and qb_starts(tq) < 4 and stat in ('passing_yards', 'receiving_yards', 'receptions')))) if on]
        log_price(dict(source='card.prop', player=player, team=team, pos=pos, stat=stat, line=line, over=over, under=under,
                       p_over_v3=round(float(p3), 4), p_over_v8=round(float(p), 4) if v8 is not None else np.nan, proj_v3=round(float(proj), 2), flags=';'.join(flags)), team)


PRICES = os.path.join(HERE, '..', 'v8', 'prices', 'dk_props.csv')
V8F = os.path.join(HERE, '..', 'v8', 'frozen.json'); V8P = os.path.join(HERE, '..', 'data', 'v8', 'pricer8.pkl')


def v8_chance(player, stat, pos, team, proj, line, wx):
    """v8 (v8/RESULTS.md): proj3 x f(team total, bad weather, key receiver out, lead RB out). Returns (p_over, proj8, inputs) or None."""
    if not (os.path.exists(V8F) and os.path.exists(V8P)):
        return None
    fz = json.load(open(V8F))['stats'].get(stat)
    if not fz or not fz['replaces_v3']:
        return None
    sys.path.insert(0, os.path.join(HERE, '..', 'v7'))
    import live
    e, c, home = next_game(team)
    od = espn_odds(c) if c else None
    itt = None
    if od and od.get('home_spread') is not None and od.get('total') is not None:
        fav = -float(od['home_spread']) if home else float(od['home_spread'])
        itt = (float(od['total']) + fav) / 2
    bad = 1.0 if v6_weather(wx) else 0.0
    out = live.outs(injuries(team)); me = live.norm(player)
    rec, rb = live.key_players(team, _pricer(stat)[2]) if out else ({}, {})
    rec_out = [rec[n] for n in rec if n in out and n != me] if pos in ('WR', 'TE') else []
    rb_out = [rb[n] for n in rb if n in out and n != me] if pos == 'RB' else []
    x = {'itt': (itt - 22) if itt is not None else 0.0, 'bad': bad, 'rec_out': float(bool(rec_out)), 'rb_out': float(bool(rb_out))}
    f = fz['coef']['const'] + sum(fz['coef'][k] * v for k, v in x.items())
    proj8 = proj * min(max(f, 0.5), 1.5)
    pr8 = pd.read_pickle(V8P)[stat]
    p8 = pr8.p_over(pos, proj8, line)
    desc = (f"team total {itt:.1f}" if itt is not None else 'team total n/a') + (', bad weather' if bad else '') + \
           (f", key receiver out: {', '.join(rec_out)}" if rec_out else '') + (f", lead RB out: {', '.join(rb_out)}" if rb_out else '')
    return p8, proj8, desc, fz


def log_price(row, team):
    """v8 DK price log (v8/PROTOCOL.md): every DK prop price priced by a tool, graded later by scoreboard.py."""
    e, c, _ = next_game(team)
    row = dict(logged_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), event=e['id'] if e else '',
               kickoff=e['date'] if e else '', game=e['shortName'] if e else '', **row, result='')
    os.makedirs(os.path.dirname(PRICES), exist_ok=True)
    new = pd.DataFrame([row])
    if os.path.exists(PRICES):
        old = pd.read_csv(PRICES, dtype=str)
        same = (old.event == str(row['event'])) & (old.player == row['player']) & (old.stat == row['stat']) & (old.line.astype(float) == float(row['line']))
        new = pd.concat([old[~same], new.astype(str)], ignore_index=True)   # latest price for the same prop wins
    new.to_csv(PRICES, index=False)


def team_props(team):
    hurt = {n: s_ for n, s_ in injuries(team).items() if s_ in BAD}
    if hurt:
        print('Left out (ESPN injury list): ' + ', '.join(f'{n} ({s_})' for n, s_ in hurt.items()))
        print('** TEAMMATES OUT: the model does not move their targets/carries to the players below - '
              'NOT VERIFIED for pass catchers/backs on this team (old v2 test: such players were under-rated 2-3%).')
    for stat in ('passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'anytime_td'):
        s, pr, d = _pricer(stat)
        last = s[s.team == team]
        if last.empty:
            continue
        cur = last[last.season == last.season.max()]
        players = cur.groupby('player_display_name').size()
        players = players[players >= 3].index
        for pl in players:
            x = next_projection(stat, pl)
            if x is None:
                continue
            pid, pos, tm_, avg, _ = x
            if tm_ != team:
                continue
            if injuries(team).get(pl) in BAD:
                continue
            avg = avg * opp_factor(stat, team, pos)[1]
            if stat == 'anytime_td':
                p = pr.p_over(pos, avg)
                print(f"{pl:24s} anytime TD  {p:.0%} (fair {props.fair_american(p)})")
            else:
                if avg < 5 and stat != 'receptions':
                    continue
                L = props.half(avg)
                p = pr.p_over(pos, avg, L)
                print(f"{pl:24s} {stat:15s} proj {avg:6.1f}  {L:g}: Over {p:.0%} ({props.fair_american(p)}) / Under {1 - p:.0%} ({props.fair_american(1 - p)})")
    print('\nProjection = weighted average x next opponent factor (same formula as the backtest).'
          '\nLEAN: props have no test against DK prices. Players Out/Doubtful/IR on ESPN are left out. The model does NOT move'
          '\nteammates\' targets/carries up when a starter is out - those players may be under-projected.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=['nfl', 'cfb', 'prop', 'props'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--week', type=int)
    ap.add_argument('--date')
    ap.add_argument('--team')
    ap.add_argument('--over', type=float)
    ap.add_argument('--under', type=float)
    o = ap.parse_args()
    if o.what == 'nfl':
        nfl_card(o.week)
    elif o.what == 'cfb':
        cfb_card(o.date)
    elif o.what == 'prop':
        price_prop(o.args[0], o.args[1], float(o.args[2]), o.over, o.under)
    else:
        team_props(o.team)
