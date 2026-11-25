"""v3 game-day card (FROZEN model, v3/frozen.json). Lines and prices: DraftKings via ESPN's free scoreboard.

  python v3/card.py nfl [--week N]            every NFL game this week: spread, winner, total + teaser legs
  python v3/card.py cfb [--date YYYYMMDD]     every FBS game that day
  python v3/card.py prop "Josh Allen" passing_yards 245.5 [--over -115 --under -105]
                                              fair price of the Over AND Under (and value at DK's price)
  python v3/card.py props --team BUF          fair prices for that team's players at lines near the projection

Labels: TESTED PICK = passed v3/PROTOCOL.md in both periods. LEAN = did not pass (shown with its record).
Every printed pick is written to v3/picks/log.csv (latest game-day run before kickoff wins).
"""
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

FROZEN = json.load(open(os.path.join(HERE, 'frozen.json')))
LOG = os.path.join(HERE, 'picks', 'log.csv')
ESPN2NFLV = {'WSH': 'WAS', 'LAR': 'LA'}
BAD = ('Out', 'Doubtful', 'Injured Reserve', 'Suspended', 'Physically Unable to Perform')


def rec(league, key):
    r = FROZEN['records'][league][key]
    lab = 'TESTED PICK' if r['pass'] else 'LEAN'
    return lab, f"{lab} (tested {r['early']} / {r['late']})"


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
            'home_ml': am(g(ml, 'home', 'close', 'odds')), 'away_ml': am(g(ml, 'away', 'close', 'odds'))}


def log_picks(rows):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = pd.DataFrame(rows)
    if os.path.exists(LOG):
        old = pd.read_csv(LOG, dtype={'event': str})
        old = old[~old.set_index(['event', 'market']).index.isin(new.set_index(['event', 'market']).index)]
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
            for n, (tab, pos, s) in inj.items():
                if pos in ('QB', 'RB', 'WR', 'TE') and s in BAD and tab == tm[side] and n != qn:
                    checks.append(f'{team} {pos} {n}: {s}')
        wx = summ.get('gameInfo', {}).get('weather')
        if wx and not c.get('venue', {}).get('indoor'):
            if (wx.get('gust') or 0) >= 20 or (wx.get('precipitation') or 0) >= 60:
                checks.append(f"weather (not in model): {wx.get('temperature')}F, gusts {wx.get('gust')} mph, precip {wx.get('precipitation')}%")
        L = -float(od['home_spread'])                       # nflverse sign: + = home favored
        x = r.copy(); x['spread_line'] = L; x['total_line'] = float(od['total'])
        pm = float(nfl._pred(bs, x[nfl.SPREAD_X].values.astype(float)[None, :])[0])
        pt = float(nfl._pred(bt, x[nfl.TOTAL_X].values.astype(float)[None, :])[0])
        edge = pm - L
        side_home = edge > 0
        sp_team, sp_line = (h, -L) if side_home else (a, L)
        sp_price = od['home_spread_odds'] if side_home else od['away_spread_odds']
        key = 'spread edge 2+' if abs(edge) >= 2 else 'spread edge 1+' if abs(edge) >= 1 else 'spread edge 0+'
        lab, rtxt = rec('nfl', key)
        ph = wp(pm, sd)
        w_team, w_p, w_price = (h, ph, od['home_ml']) if ph >= 0.5 else (a, 1 - ph, od['away_ml'])
        ev = w_p * float(grade.dec([w_price])[0]) - 1 if not np.isnan(w_price) else np.nan
        tedge = pt - x.total_line
        t_side = 'Over' if tedge > 0 else 'Under'
        t_price = od['over_odds'] if tedge > 0 else od['under_odds']
        tkey = 'total edge 2+' if abs(tedge) >= 2 else 'total edge 1+' if abs(tedge) >= 1 else 'total edge 0+'
        tlab, ttxt = rec('nfl', tkey)
        mlab, mtxt = rec('nfl', 'moneyline EV 3%+')
        print(hdr)
        print(f"  QBs (schedule): {r.get('away_qb_name')} / {r.get('home_qb_name')}")
        print(f"  SPREAD  {sp_team} {line_txt(sp_line)} ({sp_price:+.0f}, needs {be(sp_price):.1%})  model: {h if pm >= 0 else a} by {abs(pm):.1f}, edge {abs(edge):.1f}  {rtxt}")
        print(f"  WINNER  {w_team} ({w_price:+.0f}) model chance {w_p:.0%}, value at DK price {ev:+.0%}  "
              f"{'LEAN - moneyline rule (3%+ value) ' + mtxt.split(' ', 1)[1] if ev >= 0.03 else 'LEAN (under 3% value)'}")
        print(f"  TOTAL   {t_side} {x.total_line:g} ({t_price:+.0f}, needs {be(t_price):.1%})  model {pt:.1f}  {ttxt}")
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
            if be(gprice) > 0.539:
                print(f"     !! at {gprice:+.0f} DK needs {be(gprice):.1%} - above the rule's 53.9% record: NOT a bet at this price")
            rows.append(dict(league='nfl', event=e['id'], kickoff=e['date'], game=f'{a}@{h}', market='price_gap', side=gs,
                             pick=gteam, line=gline, price=gprice, label='TESTED PICK', model=round(imp, 2)))
        for ch in checks:
            print(f'  ** {ch}')
        print()
        base = dict(league='nfl', event=e['id'], kickoff=e['date'], game=f'{a}@{h}')
        rows += [dict(base, market='spread', side='home' if side_home else 'away', pick=sp_team, line=sp_line, price=sp_price, label=lab, model=round(pm, 2)),
                 dict(base, market='winner', side='home' if ph >= 0.5 else 'away', pick=w_team, line=np.nan, price=w_price, label=mlab if ev >= 0.03 else 'LEAN', model=round(w_p, 3)),
                 dict(base, market='total', side=t_side.lower(), pick=t_side, line=x.total_line, price=t_price, label=tlab, model=round(pt, 2))]
    gaps = [f"{r_['pick']} {line_txt(r_['line'])}" for r_ in rows if r_['market'] == 'price_gap']
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
    opp, opp_f = opp_factor(stat, team, pos)
    proj = avg * opp_f
    p = pr.p_over(pos, proj, line)
    cal = FROZEN['props'][stat]
    note = 'calibrated 2023-26' if cal['pass'] else f"NOT calibrated (worst gap {cal['worst_gap']:.1%} in 2023-26)"
    print(f"{player} ({team} {pos} vs {opp}, opponent factor {opp_f:.2f}) {stat} {line}: projection {proj:.1f}; Over {p:.1%} (fair {props.fair_american(p)}), "
          f"Under {1 - p:.1%} (fair {props.fair_american(1 - p)}). {note}. LEAN: beating DK prices is not tested.")
    for side, price, q in (('Over', over, p), ('Under', under, 1 - p)):
        if price is not None:
            ev = q * float(grade.dec([price])[0]) - 1
            print(f"   DK {side} {price:+.0f}: needs {be(price):.1%}, model {q:.1%} -> value {ev:+.1%}")


def team_props(team):
    hurt = {n: s_ for n, s_ in injuries(team).items() if s_ in BAD}
    if hurt:
        print('Left out (ESPN injury list): ' + ', '.join(f'{n} ({s_})' for n, s_ in hurt.items()))
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
