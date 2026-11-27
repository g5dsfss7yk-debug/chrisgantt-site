# v8 props model - results (rules: v8/PROTOCOL.md, committed first at 8e2486f)

`python v8/model.py` (Brier score, lower = better; same lines and splits as v3 amendment 4). v8 beat v3 on EVERY stat
in BOTH periods, so v8's chance is now the main number on `card.py prop` (v3 printed beside it). Frozen: v8/frozen.json
(fit 2013-22); pricers rebuilt by `python v8/freeze.py` (gameday.py does it in a fresh container).

| Stat | 2019-22 v3 / v8 | 2023-26 v3 / v8 | v8 calibrated (2023-26)? |
|---|---|---|---|
| passing yards | 0.14541 / 0.14460 | 0.15011 / 0.14952 | no (worst gap 3.3%) |
| rushing yards | 0.22269 / 0.22194 | 0.21864 / 0.21819 | yes (1.7%) |
| receiving yards | 0.22272 / 0.22229 | 0.22308 / 0.22232 | yes (2.4%) |
| receptions | 0.20882 / 0.20867 | 0.20517 / 0.20449 | **yes (2.6%) - v3 was not** |
| anytime TD | 0.17394 / 0.17362 | 0.16925 / 0.16893 | no (6.5%) |

What the fit learned (2013-22, multiplier on the v3 projection):
- Bad weather: passing -7.8%, receiving yards -9.5%, receptions -6.7%, TD -4.2%, rushing ~0.
- Key receiver out: teammates' receiving yards +21%, receptions +21%.
- Lead RB out: other RBs' rushing yards +54%, receiving yards +29%, TD chance +27%.
- Team total: almost no linear effect (TD +2% per point). The v7 team-total notes (A1/A2/A6) are NOT carried into v8 -
  per protocol the notes are dropped when v8 replaces a stat; the v7 effect may be only at the extremes (not tested).

Limits: the improvement is small (Brier ~0.3-0.5%). Still no test against DK prices - that needs the price log.

## DK price log
`v8/prices/dk_props.csv` - started Nov 26 with 129 DK prices typed from Chris's 8:32 AM CT screenshots (CHI@DET, PHI@DAL,
KC@BUF) + every `card.py prop` call with a price. Graded by `v3/scoreboard.py`. The DK test (PROTOCOL) runs at 300
graded pre-kickoff prices.
