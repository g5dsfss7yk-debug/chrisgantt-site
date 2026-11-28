"""core college card (core/PROTOCOL.md). python core/card_cfb.py EVENT_ID [EVENT_ID ...]
DK lines from ESPN (DraftKings). Every pick is LEAN (nothing passed its test). Prints every check it can; says when it
cannot. Logs to core/picks/log.csv."""
import os, sys, json, urllib.request
from datetime import datetime, timezone
from math import erf, sqrt
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data, cfb

E = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football'
LOG = os.path.join(HERE, 'picks', 'log.csv')
get = lambda u: json.load(urllib.request.urlopen(u, timeout=30))
be = lambda ml: (-ml / (-ml + 100)) if ml < 0 else (100 / (ml + 100))


def model():
    H = json.load(open(os.path.join(HERE, 'results', 'cfb_test.json')))['H']
    f = cfb.build(H).merge(cfb.extras(), on='game_id', how='left')
    for x in cfb.EXTRA_ALL:
        f[f'm_{x}'] = f[f'm_{x}'].fillna(0.0); f[f't_{x}'] = f[f't_{x}'].fillna(0.0)
    cfb.EXTRA[:] = cfb.EXTRA_ALL
    cfb.TOTAL_MODE = 'median'          # amendment 14: removes the Over lean in college totals
    tr = f[f.season.between(cfb.FIRST, 2025)]
    bm, sd = cfb.fit(tr, 'margin')
    bt, _ = cfb.fit(f[f.season.between(2023, 2025)], 'total')       # amendment 17: last 3 seasons, median total model
    # amendment 19: in-season recalibration of the margin = sum of this season's errors so far / (games + 100)
    cur = f[(f.season == 2026) & f.home_score.notna()]
    cur = cur[cfb.design(cur, 'margin').notna().all(axis=1)]
    err = (cur.home_score - cur.away_score) - cfb.design(cur, 'margin').values @ bm.values
    corr = float(err.sum() / (len(err) + 100))
    return H, bm, bt, sd, corr, len(err)


def live_ratings(H):
    tg = cfb.team_games(range(2025, 2027))
    sl = cfb.slates(tg); tg['wk'] = np.where(tg.season_type == 'postseason', 99, tg.week)
    tg = tg.merge(sl[['season', 'wk']].reset_index().rename(columns={'index': 'slate_i'}), on=['season', 'wk'])
    last = tg[tg.season == 2026].week.max()
    return cfb.ratings_for_slate(tg, H, len(sl)), int(last)


def last_game_qb(team_id):
    """ESPN: the team's most recent completed game and its passer with the most attempts."""
    s = get(f'{E}/teams/{team_id}/schedule')
    done = [e for e in s.get('events', []) if e['competitions'][0]['status']['type'].get('completed')]
    if not done:
        return None, None, None
    e = done[-1]; d = pd.Timestamp(e['date'])
    sm = get(f'{E}/summary?event={e["id"]}')
    best = None
    for t in sm.get('boxscore', {}).get('players', []):
        if str(t['team']['id']) != str(team_id):
            continue
        for st in t.get('statistics', []):
            if st.get('name') == 'passing':
                for a in st.get('athletes', []):
                    ca = a['stats'][0] if a.get('stats') else '0/0'
                    att = int(str(ca).split('/')[-1]) if '/' in str(ca) else 0
                    if best is None or att > best[1]:
                        best = (a['athlete']['displayName'], att)
    return (best[0] if best else None), d, e.get('name')


from functools import lru_cache


@lru_cache(maxsize=None)
def _pbp(seasons):
    return data.cfb_pbp(list(seasons))


@lru_cache(maxsize=None)
def _first_passers():
    pb = _pbp(tuple(range(2014, 2027)))
    return pb[(pb['pass'] == 1) & pb.passer_player_name.notna()].drop_duplicates(['game_id', 'pos_team'])


def team_state(name):
    """From the play-by-play history: latest Elo, the QB history, talent, home location."""
    pb = _pbp((2025, 2026))
    g = pb.groupby('game_id').agg(date=('start_date', 'first'), home=('home', 'first'), away=('away', 'first'),
                                  he=('home_team_pregame_elo', 'first'), ae=('away_team_pregame_elo', 'first')).sort_values('date')
    x = g[(g.home == name) | (g.away == name)]
    elo = pd.concat([x.he.where(x.home == name), x.ae.where(x.away == name)]).dropna()
    elo = float(elo.iloc[-1]) if len(elo) else np.nan
    return elo


def qb_hist(qb):
    pb = _pbp(tuple(range(2014, 2027)))
    db = pb[(pb['pass'] == 1) & (pb.passer_player_name == qb)]
    n, s = len(db), float(db.EPA.sum())
    first = _first_passers()
    starts = int((first.passer_player_name == qb).sum())
    return s / (n + 200), starts, n


def main(ids):
    H, bm, bt, sd, corr, ncorr = model()
    R, lastwk = live_ratings(H)
    tal = data.cfb_talent([2026]).set_index('team').talent
    th = data.cfb_team_home().dropna(subset=['tlat']).drop_duplicates('team').set_index('team')
    T2 = json.load(open(os.path.join(HERE, 'results', 'cfb_test2_firstqb.json')))['results']
    rec = lambda k: f"tested {T2[k]['early'][0] / max(T2[k]['early'][1], 1):.1%} of {T2[k]['early'][1]} 2017-22 / {T2[k]['late'][0] / max(T2[k]['late'][1], 1):.1%} of {T2[k]['late'][1]} 2023-26"
    now = datetime.now(timezone.utc)
    print(f"core COLLEGE card - {now:%Y-%m-%d %H:%M} UTC. DK lines from ESPN (DraftKings). Tested: totals and spreads 2+ pts off the line; everything else is a LEAN.")
    print(f"** Ratings use play-by-play through 2026 week {lastwk} only (the free data has not added later weeks).")
    print(f"** In-season recalibration: margin {corr:+.2f} pts (from {ncorr} games this season), amendment 19.")
    print("** No college injury list exists (ESPN: none) - injuries and starting lineups are NOT checked by any tool: check by hand.\n")
    rows = []
    bias = dict(over=0, total=0, fav=0, spread=0, home=0)
    for eid in ids:
        sm = get(f'{E}/summary?event={eid}')
        comp = sm['header']['competitions'][0]
        tm = {c['homeAway']: c for c in comp['competitors']}
        hn, an = tm['home']['team']['location'], tm['away']['team']['location']
        kick = pd.Timestamp(comp['date'])
        pc = next((p for p in sm.get('pickcenter', []) if p.get('provider', {}).get('name') == 'DraftKings'), None)
        print(f"{an} @ {hn}  {kick.tz_convert('America/Chicago'):%a %b %d %I:%M %p} CT")
        if comp['status']['type']['name'] != 'STATUS_SCHEDULED':
            print('  [started - not carded]\n'); continue
        if not pc:
            print('  [no DraftKings line on ESPN]\n'); continue
        sp = float(pc['spread']); tot = float(pc['overUnder'])
        hml = pc.get('homeTeamOdds', {}).get('moneyLine'); aml = pc.get('awayTeamOdds', {}).get('moneyLine')
        hsp = pc.get('homeTeamOdds', {}).get('spreadOdds'); asp = pc.get('awayTeamOdds', {}).get('spreadOdds')
        ovo, uno = pc.get('overOdds'), pc.get('underOdds')
        checks = []
        for nm in (hn, an):
            if nm not in R['pass_epa'][1].index:
                checks.append(f'NOT VERIFIED: {nm} is not in the ratings (name mismatch) - no pick')
        if any('NOT VERIFIED' in c for c in checks):
            print('  ' + '\n  '.join('** ' + c for c in checks) + '\n'); continue
        row = {'neutral': float(bool(comp.get('neutralSite'))), 'spread_med': sp, 'total_med': tot}
        for s in cfb.STATS:
            mu, off, dfn, home = R[s]; loc = 0 if row['neutral'] else 1
            he = mu + off.get(hn, 0) + dfn.get(an, 0) + home * loc; ae = mu + off.get(an, 0) + dfn.get(hn, 0) - home * loc
            row[f'm_{s}'] = he - ae; row[f't_{s}'] = he + ae
        side = {}
        for ha, nm in (('home', hn), ('away', an)):
            tid = tm[ha]['team']['id']
            qb, lastd, lastg = last_game_qb(tid)
            qv, starts, ndb = qb_hist(qb) if qb else (0.0, 0, 0)
            elo = team_state(nm)
            rest = min((kick - lastd).total_seconds() / 86400, 14) if lastd is not None else 14
            if ha == 'away' and nm in th.index and hn in th.index:
                a1, o1, a2, o2 = map(np.radians, (th.loc[nm, 'tlat'], th.loc[nm, 'tlon'], th.loc[hn, 'tlat'], th.loc[hn, 'tlon']))
                trav = 3958.8 * 2 * np.arcsin(np.sqrt(np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2)) / 1000
            else:
                trav = 0.0
            side[ha] = dict(qb_value=qv, backup_qb=float(starts < 4), qb_change=0.0, elo=elo, talent=float(tal.get(nm, tal.min())),
                            returning=0.0, rest=rest, travel=trav)
            checks.append(f"{nm} QB: {qb or 'unknown'} (most passes in last game: {lastg}; {starts} starts in the data) - "
                          f"starter NOT confirmed (no college injury/lineup data)")
            if starts < 4:
                checks.append(f'NOT VERIFIED - BACKUP QB: {qb} has {starts} starts in the data (needs 4) - spread/total NOT VERIFIED')
        for x in cfb.EXTRA_ALL:
            row[f'm_{x}'] = side['home'][x] - side['away'][x]; row[f't_{x}'] = side['home'][x] + side['away'][x]
        fr = pd.DataFrame([row])
        pm = float(cfb.predict(fr, bm, 'margin').iloc[0]) + corr; pt = float(cfb.predict(fr, bt, 'total').iloc[0])
        ph = 0.5 * (1 + erf(pm / (sd * sqrt(2))))
        exp = -sp; edge = pm - exp
        sp_team, sp_line, sp_price = (hn, sp, hsp) if edge > 0 else (an, -sp, asp)
        e2 = abs(edge) >= 2
        AP = json.load(open(os.path.join(HERE, 'results', 'approaches.json')))
        if e2:
            r_ = AP['COLLEGE|1b|spread|2']
            lab = (f"TESTED PICK (college spread 2+ pts off the line, recalibrated: {r_['p1'][0] / r_['p1'][1]:.1%} of {r_['p1'][1]} 2020-22 / "
                   f"{r_['p2'][0] / r_['p2'][1]:.1%} of {r_['p2'][1]} 2023-26; one of ~60 tests - must hold up live)")
        else:
            r_ = AP['COLLEGE|1b|spread|0']
            lab = f"LEAN (under 2 pts off the line: {r_['p1'][0] / r_['p1'][1]:.1%} / {r_['p2'][0] / r_['p2'][1]:.1%})"
        print(f"  SPREAD  {sp_team} {sp_line:+g} ({sp_price})  model: {hn if pm > 0 else an} by {abs(pm):.1f}, edge {abs(edge):.1f}  {lab}")
        wt = hn if ph >= 0.5 else an; wp_ = max(ph, 1 - ph); wml = hml if ph >= 0.5 else aml
        val = wp_ - be(float(wml)) if wml else float('nan')
        print(f"  WINNER  {wt} ({wml}) model chance {wp_:.0%}, value at DK price {val:+.0%}  LEAN ({rec('winner 3%+ value') if False else 'winner 3%+ value: ROI +19.8% / +0.7%, not proven'})")
        ou = 'Over' if pt > tot else 'Under'
        RC = json.load(open(os.path.join(HERE, 'results', 'recent.json')))
        if abs(pt - tot) >= 2:
            r_ = RC['COLLEGE|LAST 3 seasons only|total|2']
            lab = (f"TESTED PICK (college total 2+ pts off the line, last-3-season fit: {r_['p1'][0] / r_['p1'][1]:.1%} of {r_['p1'][1]} 2020-22 / "
                   f"{r_['p2'][0] / r_['p2'][1]:.1%} of {r_['p2'][1]} 2023-26; must hold up live)")
        else:
            r_ = RC['COLLEGE|LAST 3 seasons only|total|0']
            lab = f"LEAN (under 2 pts off the line: {r_['p1'][0] / r_['p1'][1]:.1%} / {r_['p2'][0] / r_['p2'][1]:.1%})"
        print(f"  TOTAL   {ou} {tot:g} ({ovo if ou == 'Over' else uno})  model {pt:.1f}, edge {abs(pt - tot):.1f}  {lab}")
        print(f"  inputs: QB value {side['away']['qb_value']:+.3f}/{side['home']['qb_value']:+.3f}, Elo {side['away']['elo']:.0f}/{side['home']['elo']:.0f}, "
              f"talent {side['away']['talent']:.0f}/{side['home']['talent']:.0f}, rest {side['away']['rest']:.0f}/{side['home']['rest']:.0f} days, "
              f"travel {side['away']['travel'] * 1000:.0f} mi (away/home)")
        # line moved 2+ since the opener (DK via ESPN)
        try:
            so = float(pc['pointSpread']['home']['open']['line']); to = float(str(pc['total']['over']['open']['line']).lstrip('ou'))
            if abs(so - sp) >= 2:
                checks.append(f'CHANGE: spread (home) moved {so:+g} -> {sp:+g} since the opener (DK via ESPN)')
            if abs(to - tot) >= 2:
                checks.append(f'CHANGE: total moved {to:g} -> {tot:g} since the opener (DK via ESPN)')
        except Exception:
            checks.append('line move vs opener: not available on ESPN - check by hand')
        v = comp.get('venue') or sm.get('gameInfo', {}).get('venue', {})
        wx = sm.get('gameInfo', {}).get('weather')
        vn = (sm.get('gameInfo', {}).get('venue', {}) or {}).get('fullName', '')
        dm = data.cfb_venues(); dm = dm[dm.name.fillna('').str.lower() == vn.lower()]
        if sm.get('gameInfo', {}).get('venue', {}).get('indoor') or (len(dm) and bool(dm.dome.iloc[0])):
            checks.append(f'weather: {vn} is a dome (ESPN/CFBD) - not a factor')
        elif wx:
            g_, pr_ = wx.get('gust') or 0, wx.get('precipitation') or 0
            msg = f"weather (ESPN forecast): {wx.get('temperature')}F, gusts {g_} mph, precip {pr_}%"
            if g_ >= 15 or pr_ >= 50:
                checks.append(msg + ' - BAD WEATHER: passing/receiving/receptions Overs NOT VERIFIED')
            else:
                checks.append(msg)
        else:
            checks.append('weather: no ESPN forecast - check by hand')
        checks.append('BET CAP: at most 3 bets on this game; never two parlay legs from the same team')
        bias['total'] += 1; bias['over'] += ou == 'Over'; bias['spread'] += 1; bias['fav'] += sp_line < 0; bias['home'] += sp_team == hn
        print('  ' + '\n  '.join('** ' + c for c in checks) + '\n')
        for mk, sd_, pk, ln, pr, ex in (('spread', 'home' if edge > 0 else 'away', sp_team, sp_line, sp_price, round(pm, 2)),
                                        ('winner', 'home' if ph >= .5 else 'away', wt, None, wml, round(wp_, 3)),
                                        ('total', ou.lower(), ou, tot, ovo if ou == 'Over' else uno, round(pt, 2))):
            rows.append(dict(league='cfb', event=eid, kickoff=comp['date'], game=f'{an}@{hn}', market=mk, side=sd_, pick=pk, line=ln,
                             price=pr, label=('TESTED PICK' if (mk == 'total' and abs(pt - tot) >= 2) or (mk == 'spread' and e2) else 'LEAN'), model=ex,
                             logged_at=now.isoformat(timespec='seconds'), result=None))
    if bias['total']:
        b = lambda k, n: bias[k] / max(bias[n], 1)
        flags = [nm for nm, v in (('Overs', b('over', 'total')), ('favorites', b('fav', 'spread')), ('home teams', b('home', 'spread'))) if v > .65 or v < .35]
        print(f"BIAS CHECK (rule 7b): Overs {b('over', 'total'):.0%} of totals, favorites {b('fav', 'spread'):.0%} and home teams "
              f"{b('home', 'spread'):.0%} of spread picks" + (f"  << past 65% one way: {', '.join(flags)}" if flags else ''))
    if rows:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        new = pd.DataFrame(rows)
        if os.path.exists(LOG):
            old = pd.read_csv(LOG, dtype={'event': str}); old = old[~old.event.isin(set(new.event))]
            new = pd.concat([old, new], ignore_index=True)
        new.to_csv(LOG, index=False)


if __name__ == '__main__':
    main(sys.argv[1:])
