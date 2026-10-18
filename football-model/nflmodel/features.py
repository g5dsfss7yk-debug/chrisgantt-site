"""Turn raw nflverse data into one row of pre-game features per game.

Everything is computed strictly from information available before kickoff:
ratings and form are updated only after a game is recorded as played.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque

import numpy as np
import pandas as pd

from . import teams

# --- tunables ---------------------------------------------------------------
ELO_K = 20
ELO_HFA = 48            # Elo points (~1.9 pts on the field)
ELO_REVERT = 1 / 3      # pull toward 1500 at each new season
FORM_ALPHA = 0.2        # EWMA weight of the most recent game
LEAGUE_PTS = 22.5       # long-run points per team per game
QB_DECAY = 0.95
QB_PRIOR = 6            # pseudo-starts of shrinkage toward 0 for QB value

# Probability an injured player misses the game, by final report status.
MISS_PROB = {"Out": 1.0, "Doubtful": 0.85, "Questionable": 0.25}

# Rough relative value of a full-time starter at each position (QB handled separately).
POS_WEIGHT = {
    "WR": 1.0, "TE": 0.7, "RB": 0.5, "HB": 0.5, "FB": 0.2,
    "T": 0.9, "G": 0.6, "C": 0.6, "OL": 0.7,
    "DE": 1.0, "DT": 0.6, "NT": 0.6, "DL": 0.8, "LB": 0.6, "ILB": 0.6, "OLB": 0.9,
    "CB": 1.0, "S": 0.7, "FS": 0.7, "SS": 0.7, "DB": 0.8,
}
OFFENSE = {"WR", "TE", "RB", "HB", "FB", "T", "G", "C", "OL"}

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def _name_key(name: str) -> str:
    s = re.sub(r"[^a-z ]", "", str(name).lower().replace("-", " "))
    return " ".join(_SUFFIX.sub("", s).split())


# --- injuries ---------------------------------------------------------------
def injury_scores(injuries: pd.DataFrame, snaps: pd.DataFrame) -> dict:
    """{(season, week, franchise): (offense_burden, defense_burden)}.

    burden = sum over injured non-QBs of P(miss) * position weight * recent snap share.
    Recent snap share uses only weeks before the report, so long-term absences that
    are already reflected in a team's form fade out naturally.
    """
    if injuries.empty:
        return {}
    snaps = snaps.copy()
    snaps["pct"] = snaps[["offense_pct", "defense_pct"]].max(axis=1)
    snaps["key"] = snaps["player"].map(_name_key)
    snaps["fr"] = snaps["team"].map(teams.franchise)
    hist = defaultdict(list)  # (fr, key) -> [(season, week, pct)] sorted
    for r in snaps[["fr", "key", "season", "week", "pct"]].itertuples(index=False):
        hist[(r.fr, r.key)].append((r.season, r.week, r.pct))
    for v in hist.values():
        v.sort()

    def share(fr, key, season, week):
        rows = hist.get((fr, key))
        if not rows:
            return 0.25  # unknown player: assume part-time contributor
        cur = [p for s, w, p in rows if s == season and w < week][-4:]
        if cur:
            return float(np.mean(cur))
        prev = [p for s, w, p in rows if s == season - 1]
        return float(np.mean(prev)) if prev else 0.25

    inj = injuries[injuries["report_status"].isin(MISS_PROB)].copy()
    inj = inj[inj["position"].isin(POS_WEIGHT)]
    sort_cols = ["date_modified"] if "date_modified" in inj else []
    inj = inj.sort_values(sort_cols).drop_duplicates(
        ["season", "week", "team", "gsis_id"], keep="last")
    out = defaultdict(lambda: [0.0, 0.0])
    for r in inj.itertuples(index=False):
        fr = teams.franchise(r.team)
        w = MISS_PROB[r.report_status] * POS_WEIGHT[r.position] * share(
            fr, _name_key(r.full_name), r.season, r.week)
        out[(r.season, r.week, fr)][0 if r.position in OFFENSE else 1] += w
    return {k: tuple(v) for k, v in out.items()}


# --- weather ----------------------------------------------------------------
def _weather(g: pd.DataFrame, overrides: dict | None) -> pd.DataFrame:
    g = g.copy()
    # Unknown roof: use the stadium's usual roof.
    usual = g.dropna(subset=["roof"]).groupby("stadium_id")["roof"].agg(lambda s: s.mode().iat[0])
    g["roof"] = g["roof"].fillna(g["stadium_id"].map(usual)).fillna("outdoors")
    g["dome"] = g["roof"].isin(["dome", "closed"]).astype(int)
    # Missing outdoor weather: stadium/month climatology from past games.
    g["month"] = g["gameday"].dt.month
    out = g[(g["dome"] == 0) & g["temp"].notna()]
    clim = out.groupby(["home_team", "month"])[["temp", "wind"]].median()
    month_clim = out.groupby("month")[["temp", "wind"]].median()
    idx = list(zip(g["home_team"], g["month"]))
    for col in ("temp", "wind"):
        fill = pd.Series([clim[col].get(i, np.nan) for i in idx], index=g.index)
        fill = fill.fillna(g["month"].map(month_clim[col]))
        g[col] = g[col].fillna(fill)
    for key, (temp, wind) in (overrides or {}).items():
        m = (g["game_id"] == key) | (g["home_team"] == key)
        m &= g["result"].isna()
        g.loc[m, ["temp", "wind"]] = [temp, wind]
    g.loc[g["dome"] == 1, ["temp", "wind"]] = [70, 0]
    g["temp"] = g["temp"].fillna(60)
    g["wind"] = g["wind"].fillna(8)
    g["cold"] = (45 - g["temp"]).clip(lower=0)
    g["heat"] = (g["temp"] - 85).clip(lower=0)
    g["high_wind"] = (g["wind"] - 10).clip(lower=0)
    g["turf"] = (~g["surface"].fillna("grass").str.contains("grass")).astype(int)
    return g


# --- main builder -----------------------------------------------------------
def build(games: pd.DataFrame, inj_scores: dict, weather_overrides: dict | None = None) -> pd.DataFrame:
    g = games[games["game_type"].isin(["REG", "WC", "DIV", "CON", "SB"])].copy()
    g["gametime"] = g["gametime"].fillna("13:00")
    g = g.sort_values(["gameday", "gametime", "game_id"]).reset_index(drop=True)
    g = _weather(g, weather_overrides)

    elo = defaultdict(lambda: 1500.0)
    off = defaultdict(lambda: LEAGUE_PTS)
    dfn = defaultdict(lambda: LEAGUE_PTS)
    last_season = {}
    recent_qbs = defaultdict(lambda: deque(maxlen=8))
    qb_starts = Counter()
    qb_val = defaultdict(float)
    qb_n = defaultdict(float)
    league_pts = 2 * LEAGUE_PTS

    rows = []
    for r in g.itertuples(index=False):
        h, a = teams.franchise(r.home_team), teams.franchise(r.away_team)
        for t in (h, a):
            if t in last_season and last_season[t] != r.season:
                elo[t] = 1500 + (elo[t] - 1500) * (1 - ELO_REVERT)
                off[t] = LEAGUE_PTS + (off[t] - LEAGUE_PTS) * 0.5
                dfn[t] = LEAGUE_PTS + (dfn[t] - LEAGUE_PTS) * 0.5
            last_season[t] = r.season
        neutral = int(r.location == "Neutral")
        elo_d = elo[h] - elo[a] + (0 if neutral else ELO_HFA)

        # Quarterbacks: missing future starter -> assume team's most recent starter.
        hq = r.home_qb_id if isinstance(r.home_qb_id, str) else (recent_qbs[h][-1] if recent_qbs[h] else None)
        aq = r.away_qb_id if isinstance(r.away_qb_id, str) else (recent_qbs[a][-1] if recent_qbs[a] else None)

        def qb_feats(team, qb):
            val = qb_val[qb] / (qb_n[qb] + QB_PRIOR) if qb else 0.0
            exp = math.log1p(min(qb_starts[qb], 50)) if qb else 0.0
            usual = Counter(recent_qbs[team]).most_common(1)
            backup = int(bool(usual) and usual[0][0] != qb and usual[0][1] >= 3)
            return val, exp, backup

        hv, he, hb = qb_feats(h, hq)
        av, ae, ab = qb_feats(a, aq)
        hi = inj_scores.get((r.season, r.week, h), (0.0, 0.0))
        ai = inj_scores.get((r.season, r.week, a), (0.0, 0.0))

        if neutral:
            away_mi = home_mi = 0.0
            tz_shift = 0
        else:
            away_mi = teams.miles(r.away_team, r.home_team)
            home_mi = 0.0
            tz_shift = teams.tz(r.home_team) - teams.tz(r.away_team)  # >0: away flew east
        kick_hr = int(str(r.gametime)[:2])
        body_clock_early = int(not neutral and kick_hr <= 13 and teams.tz(r.away_team) <= -7
                               and teams.tz(r.home_team) >= -6)
        hr, ar = r.home_rest, r.away_rest
        outdoor_cold = r.cold * (1 - r.dome)

        rows.append({
            "game_id": r.game_id, "season": r.season, "week": r.week, "game_type": r.game_type,
            "gameday": r.gameday, "gametime": r.gametime,
            "home_team": r.home_team, "away_team": r.away_team,
            "home_qb": r.home_qb_name, "away_qb": r.away_qb_name,
            "result": r.result, "total": r.total,
            "spread_line": r.spread_line, "total_line": r.total_line,
            "home_moneyline": r.home_moneyline, "away_moneyline": r.away_moneyline,
            # team strength & form
            "elo_diff": (elo[h] - elo[a]) / 25,
            "form_diff": (off[h] - dfn[h]) - (off[a] - dfn[a]),
            "off_sum": off[h] + off[a], "def_sum": dfn[h] + dfn[a],
            "league_pts": league_pts,
            # situation
            "home_field": 1 - neutral, "div_game": r.div_game,
            "rest_diff": float(np.clip(hr - ar, -7, 7)),
            "home_off_bye": int(hr >= 13), "away_off_bye": int(ar >= 13),
            "away_short_week": int(ar <= 5), "home_short_week": int(hr <= 5),
            "travel_diff": (away_mi - home_mi) / 1000, "away_tz_east": tz_shift,
            "body_clock_early": body_clock_early,
            # quarterbacks
            "qb_val_diff": hv - av, "qb_exp_diff": he - ae,
            "home_backup_qb": hb, "away_backup_qb": ab,
            # injuries (snap-weighted)
            "inj_off_diff": hi[0] - ai[0], "inj_def_diff": hi[1] - ai[1],
            "inj_off_sum": hi[0] + ai[0], "inj_def_sum": hi[1] + ai[1],
            # weather
            "dome": r.dome, "temp": r.temp, "wind": r.wind, "cold": r.cold, "heat": r.heat,
            "high_wind": r.high_wind, "turf": r.turf,
            "away_dome_team_cold": outdoor_cold * int(teams.is_dome_team(a, r.season)),
            "home_dome_team_cold": outdoor_cold * int(teams.is_dome_team(h, r.season)),
        })

        if np.isnan(r.result):
            continue
        # ---- post-game updates ----
        res = r.result
        exp = 1 / (1 + 10 ** (-elo_d / 400))
        act = 1.0 if res > 0 else (0.5 if res == 0 else 0.0)
        mult = math.log(abs(res) + 1) * 2.2 / ((elo_d if res > 0 else -elo_d) * 0.001 + 2.2)
        elo[h] += ELO_K * mult * (act - exp)
        elo[a] -= ELO_K * mult * (act - exp)
        off[h] += FORM_ALPHA * (r.home_score - off[h]); dfn[h] += FORM_ALPHA * (r.away_score - dfn[h])
        off[a] += FORM_ALPHA * (r.away_score - off[a]); dfn[a] += FORM_ALPHA * (r.home_score - dfn[a])
        league_pts += 0.01 * (r.total - league_pts)
        resid = res - elo_d / 25
        for qb, sign in ((r.home_qb_id, 1), (r.away_qb_id, -1)):
            if isinstance(qb, str):
                qb_val[qb] = QB_DECAY * qb_val[qb] + sign * resid
                qb_n[qb] = QB_DECAY * qb_n[qb] + 1
                qb_starts[qb] += 1
        if isinstance(r.home_qb_id, str):
            recent_qbs[h].append(r.home_qb_id)
        if isinstance(r.away_qb_id, str):
            recent_qbs[a].append(r.away_qb_id)

    return pd.DataFrame(rows)
