"""Game-day inputs for the v7 flags (v7/PROTOCOL.md): DK team total/spread, key receivers/RBs and defensive
starters from this season's snap counts, ESPN outs. Used by v3/card.py; prints nothing itself."""
import os, re, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
RES = os.path.join(HERE, 'results', 'v7_test.json')
V7 = json.load(open(RES)) if os.path.exists(RES) else {}
DB = {'CB', 'S', 'FS', 'SS', 'DB', 'SAF'}
BAD = {'Out', 'Doubtful', 'Injured Reserve', 'Suspended', 'Physically Unable to Perform', 'PUP'}


def norm(n):
    n = re.sub(r'[^a-z ]', '', str(n).lower())
    return ' '.join(re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', n).split())


def passed(prefix):
    """The v7 test whose name starts with prefix, if it passed."""
    for k, v in V7.items():
        if k.startswith(prefix + ' ') and v.get('passes'):
            return k, v
    return None, None


def rec_txt(v):
    if 'gap_early' in v:
        e, l = v['early'], v['late']
        return (f"{e['actual']:.0%} vs model {e['predicted']:.0%} (2019-22) / {l['actual']:.0%} vs {l['predicted']:.0%} (2023-26)")
    return (f"{v['early'][0]}/{v['early'][1]} = {v['early_pct']:.1%} / {v['late'][0]}/{v['late'][1]} = {v['late_pct']:.1%}")


def _season():
    from datetime import datetime
    n = datetime.now(); return n.year if n.month >= 7 else n.year - 1


_SN = {}


def snaps(season=None):
    season = season or _season()
    if season not in _SN:
        p = os.path.join(ROOT, 'data', 'v3', 'stats', f'snaps_{season}.parquet')
        s = pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame(columns=['game_id', 'week', 'player', 'position', 'team', 'offense_snaps', 'defense_pct'])
        s['nm'] = s.player.map(norm)
        _SN[season] = s
    return _SN[season]


def def_starters(team):
    """Defensive starters (protocol C): avg defense snap share >= 60% in the team's last 3 games, played in 2."""
    s = snaps(); s = s[(s.team == team) & (s.defense_pct > 0)]
    last = sorted(s.week.unique())[-3:]
    x = s[s.week.isin(last)]
    a = x.groupby('nm').agg(n=('defense_pct', 'size'), pct=('defense_pct', 'mean'), pos=('position', 'last'), name=('player', 'last'))
    return a[(a.n >= 2) & (a.pct >= 0.60)]


def key_players(team, weekly):
    """(key receivers, key RBs) by protocol B: >= 18% of targets / >= 50% of carries in their last 3 games played,
    and played in one of the team's last 2 games. Returns two dicts {norm name: display name}."""
    s = snaps(); s = s[(s.team == team) & (s.offense_snaps > 0)]
    wk = sorted(s.week.unique())
    recent = set(s[s.week.isin(wk[-2:])].nm)
    w = weekly[(weekly.season == _season()) & (weekly.team == team)].copy()
    if w.empty:
        return {}, {}
    tt = w.groupby('game_id')[['targets', 'carries']].sum().rename(columns={'targets': 'tt', 'carries': 'tc'})
    w = w.join(tt, on='game_id'); w['nm'] = w.player_display_name.map(norm)
    rec, rb = {}, {}
    for nm, ph in w[w.position.isin(['WR', 'TE', 'RB'])].sort_values('week').groupby('nm'):
        if nm not in recent:
            continue
        last = ph.tail(3)
        if last.targets.sum() / max(last.tt.sum(), 1) >= 0.18:
            rec[nm] = ph.player_display_name.iloc[-1]
        if ph.position.iloc[-1] == 'RB' and last.carries.sum() / max(last.tc.sum(), 1) >= 0.50:
            rb[nm] = ph.player_display_name.iloc[-1]
    return rec, rb


def outs(inj):
    return {norm(n) for n, s in inj.items() if s in BAD}
