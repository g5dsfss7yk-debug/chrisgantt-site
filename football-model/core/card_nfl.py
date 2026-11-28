"""core NFL card (core/PROTOCOL.md; CLAUDE.md rules 5-7). python core/card_nfl.py [--week N]   (default: ESPN's current week)
DraftKings lines/prices, injuries and weather from ESPN. Teaser legs (dog +1.5..+2.5) are the only NFL TESTED PICK;
spread/winner/total are LEANs with their tested records. Logs core/picks/log.csv. Prints a bias check (rule 7b)."""
import os, sys, re, json, argparse, urllib.request
from datetime import datetime, timezone
from math import erf, sqrt
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data, nfl, cfb

E = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl'
LOG = os.path.join(HERE, 'picks', 'log.csv')
ESPN2NFLV = {'LAR': 'LA', 'WSH': 'WAS', 'JAC': 'JAX'}
get = lambda u: json.load(urllib.request.urlopen(u, timeout=30))
be = lambda ml: (-ml / (-ml + 100)) if ml < 0 else (100 / (ml + 100))
toks = lambda s: ' '.join(re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', re.sub(r"[^a-z ]", '', str(s).lower().replace('-', ' ').replace('.', ' '))).split())


def model():
    H = json.load(open(os.path.join(HERE, 'results', 'nfl_test.json')))['H']
    f = nfl.build(H)
    nfl.TOTAL_MODE = 'ols'                      # amendment 15: Chris keeps the original total model
    tr = f[f.season.between(nfl.FIRST_FIT, 2025)]
    bm, sd = nfl.fit(tr, 'margin'); bt, _ = nfl.fit(tr, 'total')
    c2 = f[(f.season == 2026) & f.total.notna() & f.total_line.notna()].sort_values('gameday').tail(100)
    c2 = c2[nfl.design(c2, 'total').notna().all(axis=1)]
    tmed = float(np.median(nfl.design(c2, 'total').values @ bt.values - c2.total_line.values)) if len(c2) >= 50 else 0.0
    return H, bm, bt, sd, tmed


def live_ratings(H):
    tg = nfl.team_games(range(2025, 2027))
    sl = tg.groupby(['season', 'week']).size().reset_index()[['season', 'week']].sort_values(['season', 'week']).reset_index(drop=True)
    sl['slate_i'] = range(len(sl)); tg = tg.merge(sl, on=['season', 'week'])
    last = sl[sl.season == 2026].week.max()
    return cfb.ratings_for_slate(tg, H, len(sl)), int(last)


def depth_now():
    d = data.nfl_depth(2026, force=True)
    d = d.assign(dt=pd.to_datetime(d.dt, utc=True))
    d = d[d.dt == d.groupby('team').dt.transform('max')]
    return d[(d.pos_rank == 1) & ~d.pos_abb.isin(nfl.SPECIAL_POS) & ~d.pos_grp.eq('Special Teams')]


def qb_info(pid):
    pb = data.nfl_pbp(range(2006, 2027))
    db = pb[(pb.qb_dropback == 1) & (pb.passer_player_id == pid)]
    first = pb[(pb.qb_dropback == 1) & pb.passer_player_id.notna()].sort_values(['game_id', 'play_id']).drop_duplicates(['game_id', 'posteam'])
    return float(db.epa.sum()) / (len(db) + 200), int((first.passer_player_id == pid).sum())


def last_starter(team):
    pb = data.nfl_pbp([2026])
    x = pb[(pb.posteam == team) & (pb.qb_dropback == 1) & pb.passer_player_id.notna()].sort_values(['game_id', 'play_id'])
    if x.empty:
        return None
    g = x.game_id.max()
    return x[x.game_id == g].iloc[0].passer_player_id


def main(week=None):
    H, bm, bt, sd, tmed = model()
    R, lastwk = live_ratings(H)
    T = json.load(open(os.path.join(HERE, 'results', 'nfl_test.json')))['results']
    rec = lambda k: f"tested {T[k]['early'][0] / max(T[k]['early'][1], 1):.1%} of {T[k]['early'][1]} 2011-17 / {T[k]['late'][0] / max(T[k]['late'][1], 1):.1%} of {T[k]['late'][1]} 2018-26"
    D = depth_now()
    sch = nfl.schedule()
    q = f'&week={week}&seasontype=2' if week else ''
    sb = get(f'{E}/scoreboard?limit=50{q}')
    now = datetime.now(timezone.utc)
    print(f"core NFL card - {now:%Y-%m-%d %H:%M} UTC. DK lines/injuries/weather from ESPN. TESTED: teaser leg (dog +1.5..+2.5); everything else LEAN.")
    print(f"** Ratings use play-by-play through 2026 week {lastwk}. Totals CENTERED (amendment 22/23): recent drift {tmed:+.1f} pts removed - Overs/Unders balanced.\n")
    rows, bias = [], dict(over=0, total=0, fav=0, spread=0, home=0)
    for e in sb.get('events', []):
        comp = e['competitions'][0]; st = comp['status']['type']['name']
        tm = {c['homeAway']: c for c in comp['competitors']}
        ha, aa = tm['home']['team']['abbreviation'], tm['away']['team']['abbreviation']
        hn, an = ESPN2NFLV.get(ha, ha), ESPN2NFLV.get(aa, aa)
        kick = pd.Timestamp(comp['date'])
        print(f"{an} @ {hn}  {kick.tz_convert('America/Chicago'):%a %b %d %I:%M %p} CT")
        if st != 'STATUS_SCHEDULED':
            print(f'  [{st} - not carded]\n'); continue
        sm = get(f"{E}/summary?event={e['id']}")
        pc = next((p for p in sm.get('pickcenter', []) if p.get('provider', {}).get('name') == 'DraftKings'), None)
        if not pc or pc.get('spread') is None:
            print('  [no DraftKings line on ESPN yet]\n'); continue
        sp = float(pc['spread']); tot = float(pc['overUnder'])
        hml = pc.get('homeTeamOdds', {}).get('moneyLine'); aml = pc.get('awayTeamOdds', {}).get('moneyLine')
        hsp = pc.get('homeTeamOdds', {}).get('spreadOdds'); asp = pc.get('awayTeamOdds', {}).get('spreadOdds')
        ovo, uno = pc.get('overOdds'), pc.get('underOdds')
        checks = []
        if hn not in R['pass_epa'][1].index or an not in R['pass_epa'][1].index:
            print(f'  ** NOT VERIFIED: {hn}/{an} not in the ratings - no pick\n'); continue
        g = sch[(sch.season == 2026) & (sch.home_team == hn) & (sch.away_team == an)]
        g = g.iloc[0] if len(g) else None
        neutral = float(g.neutral) if g is not None else 0.0
        row = {'spread_home': sp, 'neutral': neutral, 'div': float(g['div']) if g is not None else 0.0, 'total_line': tot}   # ESPN spread = home number
        for s in nfl.STATS:
            mu, off, dfn, home = R[s]; loc = 0 if neutral else 1
            he = mu + off.get(hn, 0) + dfn.get(an, 0) + home * loc; ae = mu + off.get(an, 0) + dfn.get(hn, 0) - home * loc
            row[f'm_{s}'] = he - ae; row[f't_{s}'] = he + ae
        # injuries (ESPN) vs depth-chart starters
        inj = {}
        for t in sm.get('injuries', []):
            for i in t.get('injuries', []):
                inj[toks(i['athlete']['displayName'])] = (t['team']['abbreviation'], i['athlete'].get('position', {}).get('abbreviation'), i.get('status'))
        side = {}
        for hx, team, ea in (('home', hn, ha), ('away', an, aa)):
            st_ = D[D.team.isin([team, ea])]
            qb = st_[st_.pos_abb == 'QB']
            qid = qb.gsis_id.iloc[0] if len(qb) else None; qname = qb.player_name.iloc[0] if len(qb) else 'unknown'
            qstat = inj.get(toks(qname), (None, None, None))[2]
            qv, starts = qb_info(qid) if qid else (0.0, 0)
            prev = last_starter(team)
            if qstat in ('Out', 'Injured Reserve', 'Doubtful'):
                checks.append(f'NOT VERIFIED: {team} QB {qname} is {qstat} on ESPN - QB inputs use him')
            if starts < 4:
                checks.append(f'NOT VERIFIED - BACKUP QB: {qname} ({team}) has {starts} starts in the data (needs 4) - spread/total NOT VERIFIED')
            o = d_ = oq = dq = 0
            for _, p in st_[st_.pos_abb != 'QB'].iterrows():
                s_ = inj.get(toks(p.player_name), (None, None, None))[2]
                off_ = p.pos_abb in nfl.OFFENSE_POS
                if s_ in ('Out', 'Doubtful', 'Injured Reserve'):
                    o += off_; d_ += (not off_); checks.append(f'{team} starter {p.pos_abb} {p.player_name}: {s_}')
                elif s_ == 'Questionable':
                    oq += off_; dq += (not off_); checks.append(f'{team} starter {p.pos_abb} {p.player_name}: Questionable - NOT VERIFIED')
            rest = float(g.rest_h if hx == 'home' else g.rest_a) if g is not None else 7.0
            side[hx] = dict(qb_value=qv, backup_qb=float(starts < 4), qb_change=float(prev is not None and qid is not None and prev != qid),
                            off_out=o, def_out=d_, off_q=oq, def_q=dq, rest=rest)
            if side[hx]['qb_change']:
                checks.append(f'QB CHANGE: {team} starter {qname} did not start the last game - NOT VERIFIED')
        for x in nfl.EXTRA:
            row[f'm_{x}'] = side['home'][x] - side['away'][x]; row[f't_{x}'] = side['home'][x] + side['away'][x]
        # weather: ESPN forecast (gust -> wind: forecast mapping NOT tested); dome from the schedule roof
        roof = g.roof if g is not None else 'outdoors'
        wx = sm.get('gameInfo', {}).get('weather') or {}
        outdoor = roof in ('outdoors', 'open')
        row['dome'] = 0.0 if outdoor else 1.0
        if outdoor and wx:
            gust, temp, pr = wx.get('gust') or 0, wx.get('temperature'), wx.get('precipitation') or 0
            row['wind_x'] = max(gust - 10, 0); row['cold_x'] = max(40 - temp, 0) if temp is not None else 0; row['wx_missing'] = 0.0
            msg = f'weather (ESPN forecast): {temp}F, gusts {gust} mph, precip {pr}% (forecast gusts used as wind - not tested)'
            checks.append(msg + (' - BAD WEATHER: passing/receiving/receptions Overs NOT VERIFIED' if gust >= 15 or pr >= 50 else ''))
        else:
            row['wind_x'] = row['cold_x'] = 0.0; row['wx_missing'] = float(outdoor)
            checks.append('weather: dome/closed roof' if not outdoor else 'weather: no ESPN forecast - check by hand')
        fr = pd.DataFrame([row])
        nfl.TOTAL_MODE = 'ols'
        pm = float((nfl.design(fr, 'margin').values @ bm.values)[0]); pt = float((nfl.design(fr, 'total').values @ bt.values)[0])
        ph = 0.5 * (1 + erf(pm / (sd * sqrt(2))))
        edge = pm - (-sp)
        spt, spl, spp = (hn, sp, hsp) if edge > 0 else (an, -sp, asp)
        key = 'spread edge 4+' if abs(edge) >= 4 else 'spread edge 2+' if abs(edge) >= 2 else 'spread edge 0+'
        print(f"  SPREAD  {spt} {spl:+g} ({spp})  model: {hn if pm > 0 else an} by {abs(pm):.1f}, edge {abs(edge):.1f}  LEAN ({rec(key)})")
        wt = hn if ph >= .5 else an; wp_ = max(ph, 1 - ph); wml = hml if ph >= .5 else aml
        val = wp_ - be(float(wml)) if wml else float('nan')
        print(f"  WINNER  {wt} ({wml}) model chance {wp_:.0%}, value at DK price {val:+.0%}  LEAN (winner 3%+ value: ROI -7.7% / +4.1%)")
        ce = (pt - tot) - tmed
        ou = 'Over' if ce > 0 else 'Under'
        BL = json.load(open(os.path.join(HERE, 'results', 'balance.json')))
        r_ = BL['NFL (2021-23 / 2024-26)|CENTERED|' + ('2' if abs(ce) >= 2 else '0')]
        print(f"  TOTAL   {ou} {tot:g} ({ovo if ou == 'Over' else uno})  model {pt:.1f} - drift {tmed:+.1f} = centered edge {ce:+.1f}  "
              f"LEAN (centered: {r_['p1'][0] / max(r_['p1'][1], 1):.1%} 2021-23 / {r_['p2'][0] / max(r_['p2'][1], 1):.1%} 2024-26)")
        # teaser leg: dog +1.5..+2.5
        dog = (hn, sp) if sp > 0 else (an, -sp)
        tz = json.load(open(os.path.join(HERE, 'results', 'nfl_test.json')))['results']['T']
        if 1.5 <= dog[1] <= 2.5:
            print(f"  >> TEASER LEG  {dog[0]} +{dog[1]:g} -> +{dog[1] + 6:g}  TESTED PICK ({tz['early'][0] / tz['early'][1]:.1%} of {tz['early'][1]} 2011-17 / "
                  f"{tz['late'][0] / tz['late'][1]:.1%} of {tz['late'][1]} 2018-26; needs 73.9%/leg at -120 - read DK's teaser price on the slip)")
            rows.append(dict(league='nfl', event=e['id'], kickoff=comp['date'], game=f'{an}@{hn}', market='teaser_leg', side='home' if sp > 0 else 'away',
                             pick=dog[0], line=dog[1] + 6, price=None, label='TESTED PICK', model=None, logged_at=now.isoformat(timespec='seconds'), result=None))
        try:
            so = float(pc['pointSpread']['home']['open']['line']); to = float(str(pc['total']['over']['open']['line']).lstrip('ou'))
            if abs(so - sp) >= 2: checks.append(f'CHANGE: spread (home) moved {so:+g} -> {sp:+g} since the opener (DK via ESPN)')
            if abs(to - tot) >= 2: checks.append(f'CHANGE: total moved {to:g} -> {tot:g} since the opener (DK via ESPN)')
        except Exception:
            checks.append('line move vs opener: not on ESPN - check by hand')
        checks.append('BET CAP: at most 3 bets on this game; never two parlay legs from the same team. Re-run ~90 min before kickoff (inactives).')
        print('  ' + '\n  '.join('** ' + c for c in checks) + '\n')
        bias['total'] += 1; bias['over'] += ou == 'Over'; bias['spread'] += 1
        bias['fav'] += (spl < 0); bias['home'] += (spt == hn)
        for mk, sd_, pk, ln, pr_, ex in (('spread', 'home' if edge > 0 else 'away', spt, spl, spp, round(pm, 2)),
                                         ('winner', 'home' if ph >= .5 else 'away', wt, None, wml, round(wp_, 3)),
                                         ('total', ou.lower(), ou, tot, ovo if ou == 'Over' else uno, round(pt, 2))):
            rows.append(dict(league='nfl', event=e['id'], kickoff=comp['date'], game=f'{an}@{hn}', market=mk, side=sd_, pick=pk, line=ln,
                             price=pr_, label='LEAN', model=ex, logged_at=now.isoformat(timespec='seconds'), result=None))
    if bias['total']:
        b = lambda k, n: bias[k] / max(bias[n], 1)
        flags = [nm for nm, v in (('Overs', b('over', 'total')), ('favorites', b('fav', 'spread')), ('home teams', b('home', 'spread'))) if v > .65 or v < .35]
        print(f"BIAS CHECK (rule 7b): Overs {b('over', 'total'):.0%} of totals, favorites {b('fav', 'spread'):.0%} and home teams "
              f"{b('home', 'spread'):.0%} of spread picks" + (f"  << past 65% one way: {', '.join(flags)}" if flags else ''))
    if rows:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        new = pd.DataFrame(rows)
        if os.path.exists(LOG):
            old = pd.read_csv(LOG, dtype={'event': str}); old = old[~old.event.isin(set(new.event)) | old.market.eq('chris_read')]   # Chris's reads are never replaced
            new = pd.concat([old, new], ignore_index=True)
        new.to_csv(LOG, index=False)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--week', type=int)
    main(ap.parse_args().week)
