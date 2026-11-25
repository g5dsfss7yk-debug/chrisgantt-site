"""Writes v3/frozen.json from the one-time LATE results (run once after the backtests)."""
import json, os, subprocess
from datetime import date
import grade
HERE = os.path.dirname(os.path.abspath(__file__))
R = lambda n: json.load(open(os.path.join(HERE, 'results', n)))
nfl, cfbr, pr = R('nfl_results.json'), R('cfb_results.json'), R('props_results.json')
fz = {'frozen_on': str(date.today()),
      'code_commit': subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=HERE).stdout.strip(),
      'nfl': nfl['settings'] | {'grid': None}, 'cfb': cfbr['settings'] | {'grid': None},
      'records': {}, 'props': {k: {'pass': v['pass'], 'worst_gap': v['worst_gap']} for k, v in pr.items()}}
for lg, res in (('nfl', nfl), ('cfb', cfbr)):
    fz['records'][lg] = {}
    for k, v in res['results'].items():
        f = lambda r: (f"{r['pct']:.1%} of {r['n']}" + (f", ROI {r['roi']:+.1%}" if 'moneyline' in k else '')) if r['n'] else 'no bets'
        fz['records'][lg][k] = {'pass': v['pass'], 'early': f(v['early']), 'late': f(v['late'])}
for lg in ('nfl', 'cfb'):
    fz[lg].pop('grid')
json.dump(fz, open(os.path.join(HERE, 'frozen.json'), 'w'), indent=1)
print(json.dumps(fz, indent=1))
