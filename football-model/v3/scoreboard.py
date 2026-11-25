"""Live scoreboard for the FROZEN v3 model: grades v3/picks/log.csv from ESPN final scores and prints the live
record by league / bet type / label next to the tested record. $2 per pick at the logged DK price.
  python v3/scoreboard.py"""
import json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data, grade  # noqa

LOG = os.path.join(HERE, 'picks', 'log.csv')
FROZEN = json.load(open(os.path.join(HERE, 'frozen.json')))
STAKE = 2.0


def final_score(league, event):
    s = data.espn_summary(league, event)
    comp = s['header']['competitions'][0]
    if not comp.get('status', {}).get('type', {}).get('completed'):
        return None
    sc = {c['homeAway']: float(c['score']) for c in comp['competitors']}
    return sc['home'], sc['away']


def odds_final(r):
    """Value picks (event 'odds:<id>'): find the ESPN game by date + team names. Returns (home, away, scores) or None."""
    lg = 'nfl' if r.league == 'nfl' else 'college-football'
    day = pd.Timestamp(r.kickoff).tz_convert('America/New_York').strftime('%Y%m%d')
    sb = data._get_json(f'{data.ESPN}/{lg}/scoreboard?dates={day}&limit=400' + ('&groups=80' if r.league == 'cfb' else ''))
    away, home = r.game.split(' @ ')
    for e in sb.get('events', []):
        c = e['competitions'][0]
        t = {x['homeAway']: x for x in c['competitors']}
        if t['home']['team']['displayName'] == home and t['away']['team']['displayName'] == away:
            if not e['status']['type'].get('completed'):
                return None
            return home, away, (float(t['home']['score']), float(t['away']['score']))
    return None


PROP_STAT = {'player_pass_yds': [('passing', 'YDS')], 'player_rush_yds': [('rushing', 'YDS')],
             'player_reception_yds': [('receiving', 'YDS')], 'player_receptions': [('receiving', 'REC')],
             'player_anytime_td': [('rushing', 'TD'), ('receiving', 'TD')]}


def prop_result(league, espn_id, player, market):
    """Player's stat from the ESPN box score; None if the game is not final; 'void' if he has no line in the box."""
    s = data.espn_summary('nfl' if league == 'nfl' else 'cfb', espn_id)
    if not s['header']['competitions'][0].get('status', {}).get('type', {}).get('completed'):
        return None
    total, found = 0.0, False
    for tm in s.get('boxscore', {}).get('players', []):
        for grp in tm.get('statistics', []):
            for cat, lab in PROP_STAT[market]:
                if grp.get('name') != cat or lab not in grp.get('labels', []):
                    continue
                k = grp['labels'].index(lab)
                for a in grp.get('athletes', []):
                    if a['athlete']['displayName'] == player:
                        found = True
                        total += float(str(a['stats'][k]).replace(',', '') or 0)
    return total if found else 'void'


def grade_row(r, hs, as_):
    if r.market == 'total':
        t = hs + as_
        if t == r.line: return 'push'
        return 'win' if (t > r.line) == (r.side == 'over') else 'loss'
    m = (hs - as_) if r.side == 'home' else (as_ - hs)
    if r.market == 'winner':
        return 'win' if m > 0 else 'push' if m == 0 else 'loss'
    x = m + r.line
    if r.market == 'teaser_leg':
        return 'win' if x > 0 else 'loss'      # push counts as a loss (protocol)
    return 'win' if x > 0 else 'push' if x == 0 else 'loss'


def main():
    if not os.path.exists(LOG):
        print('No picks logged yet (run v3/card.py on game day).'); return
    L = pd.read_csv(LOG, dtype={'event': str})
    if 'result' not in L:
        L['result'] = np.nan
    now = pd.Timestamp.now(tz='UTC')
    todo = L[L.result.isna() & (pd.to_datetime(L.kickoff, utc=True) < now - pd.Timedelta(hours=3))]
    cache = {}
    for i, r in todo.iterrows():
        if str(r.market).startswith('prop_'):
            try:
                player, side, pt = str(r.pick).rsplit(' ', 2)
                v = prop_result(r.league, str(r.event).split(':', 1)[1], player, r.market[5:])
            except Exception:
                v = None
            if v == 'void':
                L.loc[i, 'result'] = 'void'
            elif v is not None:
                won = v > float(pt) if side == 'Over' else v < float(pt)
                L.loc[i, 'result'] = 'win' if won else 'loss'
            continue
        if str(r.event).startswith('odds:'):
            try:
                x = odds_final(r)
            except Exception:
                x = None
            if x:
                home, away, (hs_, as_) = x
                mk = {'value_spreads': 'spread', 'value_totals': 'total', 'value_h2h': 'winner'}[r.market]
                sd = r.side.lower() if mk == 'total' else ('home' if r.side == home else 'away')
                L.loc[i, 'result'] = grade_row(pd.Series({**r.to_dict(), 'market': mk, 'side': sd}), hs_, as_)
            continue
        k = (r.league, r.event)
        if k not in cache:
            try:
                cache[k] = final_score(*k)
            except Exception:
                cache[k] = None
        if cache[k]:
            L.loc[i, 'result'] = grade_row(r, *cache[k])
    L.to_csv(LOG, index=False)
    g = L[L.result.isin(['win', 'loss', 'push'])].copy()
    print(f'v3 LIVE SCOREBOARD (frozen {FROZEN["frozen_on"]}, commit {FROZEN["code_commit"]}) - '
          f'{len(g)} graded, {L.result.isna().sum()} pending')
    if g.empty:
        print('Nothing graded yet.'); return
    d = grade.dec(g.price.where(g.market != 'teaser_leg'))
    g['profit'] = np.where(g.result == 'win', STAKE * (d - 1), np.where(g.result == 'loss', -STAKE, 0.0))
    g.loc[g.market == 'teaser_leg', 'profit'] = np.nan   # legs are priced as a teaser on the slip, not alone
    for (lg, mk, lab), x in g.groupby(['league', 'market', 'label']):
        w, l, p = (x.result == 'win').sum(), (x.result == 'loss').sum(), (x.result == 'push').sum()
        pct = w / (w + l) if w + l else float('nan')
        money = '' if mk == 'teaser_leg' else f'  ${x.profit.sum():+.2f} at $2'
        print(f'  {lg.upper():3s} {mk:10s} {lab:11s} live {w}-{l}-{p} ({pct:.1%}){money}')
    print('\nTested records (EARLY / LATE): see v3/RESULTS.md. Live record counts ONLY games the frozen model never saw.')


if __name__ == '__main__':
    main()
