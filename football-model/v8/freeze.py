"""Freeze v8 (v8/PROTOCOL.md): fit f and the Pricer on 2013-22 (the LATE-tested fit), save coefficients to
v8/frozen.json and the pricers to data/v8/pricer8.pkl. python v8/freeze.py"""
import os, sys, json, subprocess
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, 'v3'))
import model, props

if __name__ == '__main__':
    ctx = model.features(); d = props.weekly()
    res = json.load(open(os.path.join(HERE, 'results', 'v8_test.json')))
    out, pr = {}, {}
    for stat in model.STATS:
        s = model.add_x(props.project(d, stat).reset_index(drop=True), ctx)
        b = model.fit(s, (2013, 2022))
        s8 = s.copy(); s8['proj'] = model.apply(s, b)
        pr[stat] = props.Pricer(s8, stat, (2013, 2022))
        out[stat] = dict(coef=dict(zip(['const'] + model.X, map(float, b))), replaces_v3=res[stat]['replaces_v3'],
                         calibrated=res[stat]['calibrated'], worst_gap=res[stat]['late']['worst_gap_v8'])
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    json.dump(dict(frozen_on='2026-11-26', code_commit=commit, train=[2013, 2022], stats=out), open(os.path.join(HERE, 'frozen.json'), 'w'), indent=1)
    os.makedirs(os.path.join(ROOT, 'data', 'v8'), exist_ok=True)
    pd.to_pickle(pr, os.path.join(ROOT, 'data', 'v8', 'pricer8.pkl'))
    print(json.dumps(out, indent=1))
