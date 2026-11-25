"""v5 price checker: DraftKings price vs a SHARP book's fair (no-vig) price. Method: the documented "+EV vs sharp
book" approach (bet the soft book when it pays more than the sharp market says the bet is worth).

  python football-model/v5/pricecheck.py nfl --markets spreads,totals,h2h      (costs 1 credit per market)
  python football-model/v5/pricecheck.py cfb --markets spreads
  python football-model/v5/pricecheck.py nfl --cached                          (re-use the last pull: 0 credits)

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('league', choices=['nfl', 'cfb'])
    ap.add_argument('--markets', default='spreads')
    ap.add_argument('--cached', action='store_true')
    ap.add_argument('--all', action='store_true', help='show every compared DK price, not only VALUE')
    o = ap.parse_args()
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
    if log:
        new = pd.DataFrame(log)
        if os.path.exists(LOG):
            old = pd.read_csv(LOG, dtype={'event': str})
            old = old[~old.set_index(['event', 'market', 'pick']).index.isin(new.set_index(['event', 'market', 'pick']).index)] \
                if 'pick' in old else old
            new = pd.concat([old, new], ignore_index=True)
        new.to_csv(LOG, index=False)
        print(f'\nLogged {len(log)} VALUE picks to v3/picks/log.csv (graded by v3/scoreboard.py).')


if __name__ == '__main__':
    main()
