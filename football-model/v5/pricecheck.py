"""v5 price checker: DraftKings price vs a SHARP book's fair (no-vig) price. Method: the documented "+EV vs sharp
book" approach (bet the soft book when it pays more than the sharp market says the bet is worth).

  python football-model/v5/pricecheck.py nfl --markets spreads,totals,h2h      (costs 1 credit per market)
  python football-model/v5/pricecheck.py cfb --markets spreads
  python football-model/v5/pricecheck.py nfl --cached                          (re-use the last pull: 0 credits)
  python football-model/v5/pricecheck.py nfl --props --hours 6 --max-credits 120
        player props for games starting within 6 hours: DK vs Pinnacle (or the no-vig median of the other books when
        Pinnacle has no price on that prop). Costs len(PROP_MARKETS) credits per game; never spends below --reserve.
        Players Out/Doubtful/IR on ESPN are dropped; Questionable flagged.

Odds API (key in env DDS_API_KEY or ODDS_API_KEY). One call returns every game of the league; cost = number of
markets (bookmakers list kept to <= 10 = one region). Free plan: 500 credits/month.

Sharp reference: Pinnacle if it lists the same line; otherwise the median no-vig chance of the other sharp books
listed (Circa, BetOnline, LowVig). Lines must MATCH exactly (DK -3 is only compared with sharp -3) - no guessing
across different numbers. Fair chance = two-way prices with the vig removed proportionally.
VALUE = DK pays at least 2% more than fair (EV >= +2%) under BOTH proportional and power vig removal. This rule is set here, before any v5 result.
NOT backtested on DK (no affordable odds history). Every VALUE pick is logged and judged on the scoreboard.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'data', 'v5'); os.makedirs(CACHE, exist_ok=True)
LOG = os.path.join(HERE, '..', 'v3', 'picks', 'log.csv')
SPORT = {'nfl': 'americanfootball_nfl', 'cfb': 'americanfootball_ncaaf'}
SHARP = ['pinnacle', 'circasports', 'betonlineag', 'lowvig']
SOFT = 'draftkings'
BOOKS = SHARP + [SOFT, 'fanduel']          # <= 10 books = 1 region-equivalent
EV_MIN = 0.02
PROP_MARKETS = ['player_pass_yds', 'player_rush_yds', 'player_reception_yds', 'player_receptions', 'player_anytime_td']
PROP_BOOKS = ['pinnacle', 'draftkings', 'fanduel', 'betmgm', 'williamhill_us', 'betrivers', 'espnbet', 'fanatics', 'betonlineag', 'lowvig']
BAD = ('Out', 'Doubtful', 'Injured Reserve', 'Suspended', 'Physically Unable to Perform')


def key():
    k = os.environ.get('ODDS_API_KEY') or os.environ.get('DDS_API_KEY')
    if not k:
        sys.exit('No Odds API key in ODDS_API_KEY / DDS_API_KEY.')
    return k


def pull(league, markets, cached):
    path = os.path.join(CACHE, f'{league}_{markets.replace(",", "_")}.json')
    if cached:
        if not os.path.exists(path):
            sys.exit(f'No cached pull at {path}. Run without --cached (costs {len(markets.split(","))} credit(s)).')
        d = json.load(open(path))
        print(f"Using cached pull from {d['pulled_at']} (0 credits).")
        return d
    q = {'apiKey': key(), 'markets': markets, 'oddsFormat': 'american', 'bookmakers': ','.join(BOOKS)}
    url = f'https://api.the-odds-api.com/v4/sports/{SPORT[league]}/odds?{urllib.parse.urlencode(q)}'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'football-model-v5'}), timeout=60) as r:
        events = json.load(r)
        rem, last = r.headers.get('x-requests-remaining'), r.headers.get('x-requests-last')
    d = {'pulled_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'events': events,
         'credits_remaining': rem, 'credits_cost': last}
    json.dump(d, open(path, 'w'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M')
    json.dump(d, open(os.path.join(CACHE, f'{league}_{markets.replace(",", "_")}_{stamp}.json'), 'w'))  # archive
    print(f'Pulled {len(events)} games. Cost {last} credit(s); {rem} left this month.')
    return d


def dec(a):
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def novig(p1, p2):
    """Fair chance of side 1. Returns the LOWER of two standard vig-removal methods (proportional and power):
    the proportional method overrates longshots (books load more margin on them), so a VALUE flag has to hold under
    both. (Amended Nov 25 before any v5 pick was graded: PHI +364 / TEN +780 were +2.4% / +2.2% proportional,
    -5.1% / -18.3% power.)"""
    i1, i2 = 1 / dec(p1), 1 / dec(p2)
    prop = i1 / (i1 + i2)
    lo, hi = 0.2, 5.0
    for _ in range(60):                      # power method: i1^k + i2^k = 1
        k = (lo + hi) / 2
        if i1 ** k + i2 ** k > 1: lo = k
        else: hi = k
    return min(prop, i1 ** k)


def rows_for(events, market):
    """One row per (game, book, outcome side) with the two-way partner price."""
    out = []
    for e in events:
        for b in e.get('bookmakers', []):
            for m in b.get('markets', []):
                if m['key'] != market or len(m['outcomes']) != 2:
                    continue
                o1, o2 = m['outcomes']
                for a, z in ((o1, o2), (o2, o1)):
                    out.append({'event': e['id'], 'kick': e['commence_time'], 'game': f"{e['away_team']} @ {e['home_team']}",
                                'book': b['key'], 'side': a['name'], 'point': a.get('point'), 'price': a['price'],
                                'other_price': z['price'], 'other_point': z.get('point')})
    return pd.DataFrame(out)


def check(d, market):
    r = rows_for(d['events'], market)
    if r.empty:
        return pd.DataFrame()
    r['fair'] = [novig(a, b) for a, b in zip(r.price, r.other_price)]
    now = pd.Timestamp.now(tz='UTC')
    res = []
    dk = r[r.book == SOFT]
    for _, x in dk.iterrows():
        if pd.Timestamp(x.kick) <= now:
            continue
        same = r[(r.event == x.event) & (r.side == x.side) & (r.book.isin(SHARP))]
        if x.point is not None and not pd.isna(x.point):
            same = same[same.point == x.point]
        if same.empty:
            continue
        if 'pinnacle' in same.book.values:
            fair, src = float(same[same.book == 'pinnacle'].fair.iloc[0]), 'Pinnacle'
        else:
            fair, src = float(same.fair.median()), '+'.join(same.book)
        ev = fair * dec(x.price) - 1
        res.append({**x.to_dict(), 'fair_p': fair, 'sharp': src, 'ev': ev, 'need': 1 / dec(x.price)})
    return pd.DataFrame(res)


def fmt_side(x, market):
    if market == 'spreads':
        return f"{x.side} {x.point:+g}"
    if market == 'totals':
        return f"{x.side} {x.point:g}"
    return f"{x.side} ML"


def credits_left():
    """Free call (the sports list costs 0 credits). Returns remaining credits as int."""
    url = f'https://api.the-odds-api.com/v4/sports?apiKey={key()}'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'football-model-v5'}), timeout=60) as r:
        return int(float(r.headers.get('x-requests-remaining') or 0))


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'football-model-v5'}), timeout=60) as r:
        return json.load(r), r.headers.get('x-requests-remaining'), r.headers.get('x-requests-last')


def espn_injuries(league, home_name):
    """{player: status} for the ESPN game whose home team displayName == home_name (Odds API uses the same names)."""
    sys.path.insert(0, os.path.join(HERE, '..', 'v3'))
    import data
    lg = 'nfl' if league == 'nfl' else 'college-football'
    sb = data._get_json(f'{data.ESPN}/{lg}/scoreboard?limit=400' + ('&groups=80' if league == 'cfb' else ''))
    for e in sb.get('events', []):
        t = {x['homeAway']: x['team']['displayName'] for x in e['competitions'][0]['competitors']}
        if t.get('home') == home_name:
            s = data.espn_summary(league, e['id'])
            return {i['athlete']['displayName']: i.get('status') for tm in s.get('injuries', []) for i in tm['injuries']}, e['id']
    return {}, None


def prop_rows(ev):
    """Two-way Over/Under rows per (book, market, player, point)."""
    out = []
    for b in ev.get('bookmakers', []):
        for m in b.get('markets', []):
            byk = {}
            for o in m['outcomes']:
                byk.setdefault((o.get('description'), o.get('point')), {})[o['name']] = o['price']
            for (pl, pt), d in byk.items():
                if 'Over' in d and 'Under' in d:
                    for side, other in (('Over', 'Under'), ('Under', 'Over')):
                        out.append({'book': b['key'], 'market': m['key'], 'player': pl, 'point': pt, 'side': side,
                                    'price': d[side], 'other_price': d[other]})
                elif m['key'] == 'player_anytime_td' and ('Yes' in d or 'Over' in d):
                    pass  # one-sided TD prices cannot be de-vigged; skipped
    return pd.DataFrame(out)


def check_props(ev, inj):
    r = prop_rows(ev)
    if r.empty:
        return pd.DataFrame()
    r['fair'] = [novig(a, b) for a, b in zip(r.price, r.other_price)]
    res = []
    for _, x in r[r.book == SOFT].iterrows():
        st = inj.get(x.player)
        if st in BAD:
            continue
        same = r[(r.book != SOFT) & (r.market == x.market) & (r.player == x.player) & (r.point == x.point) & (r.side == x.side)]
        if same.empty:
            continue
        if 'pinnacle' in same.book.values:
            fair, src = float(same[same.book == 'pinnacle'].fair.iloc[0]), 'Pinnacle'
        elif len(same) >= 3:
            fair, src = float(same.fair.median()), f'median of {len(same)} books'
        else:
            continue
        ev_ = fair * dec(x.price) - 1
        res.append({**x.to_dict(), 'fair_p': fair, 'sharp': src, 'ev': ev_, 'need': 1 / dec(x.price), 'injury': st})
    return pd.DataFrame(res)


def run_props(league, hours, max_credits, reserve, show_all):
    ev_list, _, _ = _get(f'https://api.the-odds-api.com/v4/sports/{SPORT[league]}/events?apiKey={key()}')  # free
    now = pd.Timestamp.now(tz='UTC')
    ev_list = [e for e in ev_list if now < pd.Timestamp(e['commence_time']) <= now + pd.Timedelta(hours=hours)]
    left = credits_left()
    cost = len(PROP_MARKETS)
    print(f'{len(ev_list)} {league.upper()} games start within {hours}h. Credits left: {left}. Props cost {cost} per game.')
    spent, log = 0, []
    for e in sorted(ev_list, key=lambda e: e['commence_time']):
        if spent + cost > max_credits or left - cost < reserve:
            print(f"  SKIPPED {e['away_team']} @ {e['home_team']}: credit limit (left {left}, reserve {reserve}, run cap {max_credits})")
            continue
        q = {'apiKey': key(), 'markets': ','.join(PROP_MARKETS), 'oddsFormat': 'american', 'bookmakers': ','.join(PROP_BOOKS)}
        d, rem, last = _get(f"https://api.the-odds-api.com/v4/sports/{SPORT[league]}/events/{e['id']}/odds?{urllib.parse.urlencode(q)}")
        left, spent = int(float(rem or 0)), spent + int(float(last or cost))
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M')
        json.dump(d, open(os.path.join(CACHE, f"{league}_props_{e['id']}_{stamp}.json"), 'w'))
        inj, espn_id = espn_injuries(league, e['home_team'])
        c = check_props(d, inj)
        kick = pd.Timestamp(e['commence_time']).tz_convert('America/Chicago')
        print(f"\n{e['away_team']} @ {e['home_team']}  {kick:%a %I:%M%p} CT")
        out_players = [n for n, s_ in inj.items() if s_ in BAD]
        if out_players:
            print('  Out/IR on ESPN (no props): ' + ', '.join(out_players))
            print('  ** TEAMMATES OUT: books move their usage to others; the sharp price already includes it.')
        if c.empty:
            print('  no DK prop with a matching sharp/consensus price'); continue
        c = c.sort_values('ev', ascending=False)
        show = c if show_all else c[c.ev >= EV_MIN]
        print(f'  compared {len(c)} DK prop prices; {int((c.ev >= EV_MIN).sum())} VALUE')
        for _, x in show.iterrows():
            tag = 'VALUE' if x.ev >= EV_MIN else '     '
            q_ = f' [{x.injury} - NOT VERIFIED]' if isinstance(x.injury, str) else ''
            print(f"  {tag} {x.player:22s} {x.market.replace('player_', ''):15s} {x.side} {x.point:g} DK {x.price:+.0f} needs "
                  f"{x.need:.1%} | fair {x.fair_p:.1%} ({x.sharp}) | EV {x.ev:+.1%}{q_}")
            if x.ev >= EV_MIN and not isinstance(x.injury, str):
                log.append(dict(league=league, event=f'espn:{espn_id}' if espn_id else f"odds:{e['id']}", kickoff=e['commence_time'],
                                game=f"{e['away_team']} @ {e['home_team']}", market=f'prop_{x.market}', side=x.side,
                                pick=f'{x.player} {x.side} {x.point:g}', line=x.point, price=x.price, label='VALUE (v5, untested)',
                                model=round(x.fair_p, 4), logged_at=datetime.now(timezone.utc).isoformat(timespec='seconds')))
    print(f'\nSpent {spent} credits this run; {left} left.')
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('league', choices=['nfl', 'cfb'])
    ap.add_argument('--markets', default='spreads')
    ap.add_argument('--cached', action='store_true')
    ap.add_argument('--all', action='store_true', help='show every compared DK price, not only VALUE')
    ap.add_argument('--props', action='store_true')
    ap.add_argument('--hours', type=float, default=6)
    ap.add_argument('--max-credits', type=int, default=120)
    ap.add_argument('--reserve', type=int, default=3)
    ap.add_argument('--credits', action='store_true', help='print credits left (free) and exit')
    o = ap.parse_args()
    if o.credits:
        print('Odds API credits left:', credits_left()); return
    if o.props:
        log = run_props(o.league, o.hours, o.max_credits, o.reserve, o.all)
        return _write_log(log)
    need = len(o.markets.split(','))
    if not o.cached:
        left = credits_left()
        if left - need < 0:
            sys.exit(f'Only {left} Odds API credits left; this pull needs {need}. Use --cached or wait for the monthly reset.')
    d = pull(o.league, o.markets, o.cached)
    log = []
    print(f"\n{o.league.upper()} DraftKings vs sharp no-vig price (pulled {d['pulled_at']} UTC). VALUE = EV >= +{EV_MIN:.0%} under both vig-removal methods.")
    print('Method is the documented +EV-vs-sharp approach; NOT backtested on DK here - judged live on the scoreboard.\n')
    for mk in o.markets.split(','):
        c = check(d, mk)
        if c.empty:
            print(f'[{mk}] no DK price with a matching sharp line.'); continue
        c = c.sort_values('ev', ascending=False)
        show = c if o.all else c[c.ev >= EV_MIN]
        print(f'[{mk}] compared {len(c)} DK prices; {int((c.ev >= EV_MIN).sum())} VALUE')
        for _, x in show.iterrows():
            tag = 'VALUE' if x.ev >= EV_MIN else '     '
            kick = pd.Timestamp(x.kick).tz_convert('America/Chicago')
            print(f"  {tag} {x.game:40s} {kick:%a %I:%M%p}  DK {fmt_side(x, mk):24s} {x.price:+5.0f} needs {x.need:.1%} | "
                  f"fair {x.fair_p:.1%} ({x.sharp}) | EV {x.ev:+.1%}")
            if x.ev >= EV_MIN:
                log.append(dict(league=o.league, event=f'odds:{x.event}', kickoff=x.kick, game=x.game, market=f'value_{mk}',
                                side=x.side, pick=fmt_side(x, mk), line=x.point, price=x.price, label='VALUE (v5, untested)',
                                model=round(x.fair_p, 4), logged_at=d['pulled_at']))
    _write_log(log)


def _write_log(log):
    if log:
        new = pd.DataFrame(log)
        if os.path.exists(LOG):
            old = pd.read_csv(LOG, dtype={'event': str})
            old = old[~old.set_index(['event', 'market', 'pick']).index.isin(new.set_index(['event', 'market', 'pick']).index)] \
                if 'pick' in old else old
            new = pd.concat([old, new], ignore_index=True)
        new.to_csv(LOG, index=False)
        print(f'\nLogged {len(log)} VALUE picks to v3/picks/log.csv (graded by v3/scoreboard.py).')
    return None


if __name__ == '__main__':
    main()
