"""Chris's betting app for the Raspberry Pi (one card: v11 games + tested picks + every check; v8 props; scoreboard).
python pi/app.py  ->  open http://<pi-address>:8080 on your phone (same Wi-Fi)."""
import sys as _sys
_sys.exit('RETIRED Nov 28 2026 - Chris: "There should be no old models picking anything". Use football-model/core/ (core/HANDOFF.md).')
import os, sys, html, subprocess, threading, json
from datetime import datetime
from flask import Flask, request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); PY = sys.executable
OUT = os.path.join(ROOT, 'data', 'pi'); os.makedirs(OUT, exist_ok=True)
app = Flask(__name__)
STATS = ['receptions', 'receiving_yards', 'rushing_yards', 'passing_yards', 'anytime_td']
RUNNING = {}

CSS = """<meta name=viewport content="width=device-width,initial-scale=1"><style>
body{font-family:-apple-system,system-ui,sans-serif;margin:0;padding:12px 16px;background:#f6f6f4;color:#1b1b1b}
@media(prefers-color-scheme:dark){body{background:#151515;color:#e8e8e8}input,select{background:#222;color:#eee}}
nav a{margin-right:14px;font-weight:600}pre{white-space:pre-wrap;font-size:13px;line-height:1.35}
input,select,button{font-size:16px;padding:6px;margin:3px 0;width:100%;box-sizing:border-box}
.row{display:flex;gap:8px}.row>*{flex:1}.note{opacity:.7;font-size:13px}</style>"""
NAV = "<nav><a href='/'>Card</a><a href='/prop'>Prop</a><a href='/scoreboard'>Scoreboard</a></nav>"


def page(title, body):
    return f"<!doctype html><title>{title}</title>{CSS}{NAV}<h2>{title}</h2>{body}"


def run(args, timeout=1800):
    r = subprocess.run([PY, '-W', 'ignore'] + args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return (r.stdout + (('\n' + r.stderr[-3000:]) if r.returncode else '')).strip()


def this_week():
    sys.path.insert(0, os.path.join(ROOT, 'v3')); import data
    g = data.nfl_games(refresh_hours=6); s = int(g[g.result.notna()].season.max())
    up = g[(g.season == s) & g.result.isna()].sort_values('gameday')
    return int(up.iloc[0].week) if not up.empty else None


def bg(name, fn):
    if RUNNING.get(name):
        return
    def go():
        RUNNING[name] = True
        try:
            fn()
        finally:
            RUNNING[name] = False
    threading.Thread(target=go, daemon=True).start()


def card_job():
    wk = this_week()
    txt = run(['v3/card.py', 'nfl'] + (['--week', str(wk)] if wk else []))
    open(os.path.join(OUT, 'card.txt'), 'w').write(f"Run {datetime.now():%a %b %d %I:%M %p}\n\n{txt}")


@app.route('/', methods=['GET', 'POST'])
def card():
    if request.method == 'POST':
        bg('card', card_job)
    p = os.path.join(OUT, 'card.txt')
    txt = open(p).read() if os.path.exists(p) else 'No card yet - press Refresh.'
    busy = '<p class=note>Refreshing... reload in a minute or two.</p>' if RUNNING.get('card') else ''
    return page('NFL card', f"<form method=post><button>Refresh card now (inactives, weather, lines)</button></form>{busy}"
                f"<p class=note>Bet only TESTED PICKs; skip anything NOT VERIFIED. Max 3 bets a game.</p><pre>{html.escape(txt)}</pre>")


@app.route('/prop', methods=['GET', 'POST'])
def prop():
    f = request.form
    out = ''
    if request.method == 'POST' and f.get('player') and f.get('line'):
        args = ['v3/card.py', 'prop', f['player'].strip(), f['stat'], f['line'].strip()]
        for side in ('over', 'under'):
            if f.get(side, '').strip():
                args += [f'--{side}', f[side].strip()]
        out = f"<pre>{html.escape(run(args, 600))}</pre>"
    opts = ''.join(f"<option {'selected' if f.get('stat') == s else ''}>{s}</option>" for s in STATS)
    v = lambda k: html.escape(f.get(k, ''))
    return page('Price a prop', f"""<form method=post>
<input name=player placeholder="Player (e.g. Dawson Knox)" value="{v('player')}">
<select name=stat>{opts}</select>
<input name=line placeholder="Line: 1.5 for 2+ catches, 0.5 for anytime TD" value="{v('line')}" inputmode=decimal>
<div class=row><input name=over placeholder="DK Over price (e.g. 116)" value="{v('over')}" inputmode=numeric>
<input name=under placeholder="DK Under price (e.g. -140)" value="{v('under')}" inputmode=numeric></div>
<button>Price it</button></form><p class=note>Every DK price you enter is saved to the price log (the DK test needs 300).</p>{out}""")


@app.route('/scoreboard')
def scoreboard():
    return page('Scoreboard', f"<pre>{html.escape(run(['v3/scoreboard.py'], 900))}</pre>")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
