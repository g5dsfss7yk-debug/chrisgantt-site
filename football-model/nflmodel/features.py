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
EPA_ALPHA = 0.15        # EWMA weight for play-level efficiency
SEASON_REVERT = 0.5     # share of last season's form/efficiency kept at a new season
EARLY_K = None          # early season: EWMA weight is at least 1 / (games played + EARLY_K)
LEAGUE_SR = 0.45        # long-run success rate per play
PYTHAG_EXP = 2.37
REF_PRIOR = 30          # pseudo-games shrinking a referee's crew tendencies toward 0

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


# --- roster continuity -------------------------------------------------------
DEFAULT_CONTINUITY = (0.65, 0.65, 0.1, 0.1)


def roster_continuity(snaps: pd.DataFrame, rosters: pd.DataFrame) -> dict:
    """{(season, franchise): (returning_off, returning_def, added_off, added_def)}.

    returning = share of the team's previous-season offensive/defensive snaps played by
    players on its season-opening roster; added = previous-season snaps (in team-seasons)
    those roster players played for other teams. Low returning / high added = a rebuilt
    team whose prior-year ratings are stale.
    """
    if snaps.empty or rosters.empty:
        return {}
    sn = snaps[snaps["game_type"] == "REG"].copy()
    sn["fr"] = sn["team"].map(teams.franchise)
    sn["key"] = sn["player"].map(_name_key)
    by = sn.groupby(["season", "fr", "pfr_player_id", "key"])[["offense_snaps", "defense_snaps"]].sum()
    by = by.reset_index()
    totals = by.groupby(["season", "fr"])[["offense_snaps", "defense_snaps"]].sum()
    ro = rosters.copy()
    ro["fr"] = ro["team"].map(teams.franchise)
    ro["key"] = ro["full_name"].map(_name_key)
    out = {}
    for season, rs in ro.groupby("season"):
        prev = by[by["season"] == season - 1]
        if prev.empty:
            continue
        tot = totals.loc[season - 1]
        avg = tot.mean()
        id_rows = prev.set_index("pfr_player_id")
        name_rows = prev.set_index("key")
        for fr, team_r in rs.groupby("fr"):
            ids = set(team_r["pfr_id"].dropna())
            names = set(team_r.loc[team_r["pfr_id"].isna(), "key"])
            hit = pd.concat([id_rows[id_rows.index.isin(ids)], name_rows[name_rows.index.isin(names)]])
            own = hit[hit["fr"] == fr][["offense_snaps", "defense_snaps"]].sum()
            other = hit[hit["fr"] != fr][["offense_snaps", "defense_snaps"]].sum()
            if fr not in tot.index:
                continue
            t = tot.loc[fr]
            out[(season, fr)] = (own.offense_snaps / t.offense_snaps, own.defense_snaps / t.defense_snaps,
                                 other.offense_snaps / avg.offense_snaps,
                                 other.defense_snaps / avg.defense_snaps)
    return out


# --- weather ----------------------------------------------------------------
_GUST = re.compile(r"gust\w*\s*(?:to|of|up to)?\s*(\d+)")


def _precip(text) -> tuple[float, float, float]:
    """(rain, snow, gust mph or nan) from a play-by-play weather description."""
    if not isinstance(text, str):
        return 0.0, 0.0, np.nan
    t = text.lower()
    chance = 0.5 if re.search(r"chance|possible|scattered|\d+% (?:rain|precip)", t) else 1.0
    no = re.search(r"\bno (?:rain|precip)", t)
    rain = 0.0 if no else chance * bool(re.search(r"rain|shower|drizzle|storm|wet", t))
    snow = 0.0 if no else chance * bool(re.search(r"snow|flurr|sleet|wintry", t))
    m = _GUST.search(t)
    return rain, snow, float(m.group(1)) if m else np.nan


def _weather(g: pd.DataFrame, overrides: dict | None, wx: pd.DataFrame | None = None) -> pd.DataFrame:
    g = g.copy()
    desc = dict(zip(wx["game_id"], wx["weather"])) if wx is not None and not wx.empty else {}
    parsed = [_precip(desc.get(i)) for i in g["game_id"]]
    g["rain"] = [p[0] for p in parsed]
    g["snow"] = [p[1] for p in parsed]
    g["gust"] = [p[2] for p in parsed]
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
    for key, ov in (overrides or {}).items():
        m = (g["game_id"] == key) | (g["home_team"] == key)
        m &= g["result"].isna()
        g.loc[m, ["temp", "wind"]] = [ov["temp"], ov["wind"]]
        g.loc[m, "gust"] = ov.get("gust", np.nan)
        g.loc[m, "rain"] = ov.get("rain", 0.0)
        g.loc[m, "snow"] = ov.get("snow", 0.0)
    g["gust"] = g["gust"].fillna(g["wind"]).clip(lower=g["wind"])
    g.loc[g["dome"] == 1, ["temp", "wind", "gust", "rain", "snow"]] = [70, 0, 0, 0.0, 0.0]
    g["temp"] = g["temp"].fillna(60)
    g["wind"] = g["wind"].fillna(8)
    g["cold"] = (45 - g["temp"]).clip(lower=0)
    g["heat"] = (g["temp"] - 85).clip(lower=0)
    g["high_wind"] = (g["wind"] - 10).clip(lower=0)
    g["gusty"] = (g["gust"] - 20).clip(lower=0)
    g["turf"] = (~g["surface"].fillna("grass").str.contains("grass")).astype(int)
    return g


# --- main builder -----------------------------------------------------------
def _pbp_index(pbp: pd.DataFrame | None) -> dict:
    """{(game_id, franchise): (epa/play, success rate, giveaways)}."""
    if pbp is None or pbp.empty:
        return {}
    return {(r.game_id, teams.franchise(r.team)): (r.epa, r.sr, r.giveaways)
            for r in pbp.itertuples(index=False)}


def build(games: pd.DataFrame, inj_scores: dict, weather_overrides: dict | None = None,
          pbp: pd.DataFrame | None = None, continuity: dict | None = None,
          weather_text: pd.DataFrame | None = None, nfelo: pd.DataFrame | None = None) -> pd.DataFrame:
    g = games[games["game_type"].isin(["REG", "WC", "DIV", "CON", "SB"])].copy()
    g["gametime"] = g["gametime"].fillna("13:00")
    g = g.sort_values(["gameday", "gametime", "game_id"]).reset_index(drop=True)
    g = _weather(g, weather_overrides, weather_text)

    elo = defaultdict(lambda: 1500.0)
    off = defaultdict(lambda: LEAGUE_PTS)
    dfn = defaultdict(lambda: LEAGUE_PTS)
    last_season = {}
    recent_qbs = defaultdict(lambda: deque(maxlen=8))
    qb_starts = Counter()
    qb_val = defaultdict(float)
    qb_n = defaultdict(float)
    league_pts = 2 * LEAGUE_PTS
    plays = _pbp_index(pbp)
    # Opponent-adjusted efficiency (offense: EPA/SR gained above average; defense: allowed).
    o_epa, d_epa = defaultdict(float), defaultdict(float)
    o_sr, d_sr = defaultdict(float), defaultdict(float)
    to_margin = defaultdict(float)   # EWMA takeaways - giveaways (mostly luck)
    season_rec = defaultdict(lambda: [0.0, 0.0, 0.0, 0])  # pts for, pts against, wins, games
    season_tot_n = 3        # pseudo-games of league average shrinking this-season game totals
    continuity = continuity or {}
    nf = {}
    if nfelo is not None and not nfelo.empty:
        for x in nfelo.itertuples(index=False):
            nf[(x.season, x.week, x.home_fr, x.away_fr)] = (
                (x.starting_nfelo_home - x.starting_nfelo_away) / 25,
                (x.home_538_qb_adj - x.away_538_qb_adj) / 25,
                x.home_line_open - x.home_line_close)  # >0: line moved toward the home team
    ref_tot = defaultdict(float)     # referee -> summed (total - total line) in his games
    ref_mar = defaultdict(float)     # referee -> summed (home margin - spread line)
    ref_n = Counter()
    coach = {}                       # franchise -> current head coach
    coach_games = Counter()          # (franchise, coach) -> games coached for that team
    qb_team_starts = Counter()       # (qb, franchise) -> starts for that team

    rows = []
    for r in g.itertuples(index=False):
        h, a = teams.franchise(r.home_team), teams.franchise(r.away_team)
        for t in (h, a):
            if t in last_season and last_season[t] != r.season:
                elo[t] = 1500 + (elo[t] - 1500) * (1 - ELO_REVERT)
                off[t] = LEAGUE_PTS + (off[t] - LEAGUE_PTS) * SEASON_REVERT
                dfn[t] = LEAGUE_PTS + (dfn[t] - LEAGUE_PTS) * SEASON_REVERT
                for d in (o_epa, d_epa, o_sr, d_sr):
                    d[t] *= SEASON_REVERT
                to_margin[t] = 0.0
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

        def change(t, qb, head_coach):
            """Roster/coach/QB turnover and how stale the carried-over ratings are."""
            ro, rd, ao, ad = continuity.get((r.season, t), DEFAULT_CONTINUITY)
            hc = head_coach if isinstance(head_coach, str) else coach.get(t)
            tenure = coach_games[(t, hc)]
            new_qb = int(bool(qb) and qb_team_starts[(qb, t)] < 4)
            played = season_rec[(r.season, t)][3]
            churn = (1 - (ro + rd) / 2) + 0.15 * (tenure < 17) + 0.15 * new_qb
            stale = churn * 0.7 ** played   # fades as this season's games come in
            return ro, rd, ao, ad, math.log1p(tenure), new_qb, stale

        nfe = nf.get((r.season, r.week, h, a), ((elo[h] - elo[a]) / 25, 0.0, 0.0))
        ref = r.referee if isinstance(r.referee, str) else None
        ref_d = (ref_n[ref] + REF_PRIOR) if ref else 1.0

        hc_ = change(h, hq, r.home_coach)
        ac_ = change(a, aq, r.away_coach)

        def luck(t):
            """Season wins above Pythagorean expectation, per game (close-game luck)."""
            pf, pa, w, n = season_rec[(r.season, t)]
            if n == 0 or pf + pa == 0:
                return 0.0
            exp_w = pf ** PYTHAG_EXP / (pf ** PYTHAG_EXP + pa ** PYTHAG_EXP)
            return (w / n - exp_w) * min(n, 8) / 8
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
            # play-level efficiency, turnover luck, close-game luck
            "epa_diff": 100 * ((o_epa[h] - d_epa[h]) - (o_epa[a] - d_epa[a])),
            "sr_diff": 100 * ((o_sr[h] - d_sr[h]) - (o_sr[a] - d_sr[a])),
            "epa_off_sum": 100 * (o_epa[h] + o_epa[a]), "epa_def_sum": 100 * (d_epa[h] + d_epa[a]),
            "sr_off_sum": 100 * (o_sr[h] + o_sr[a]), "sr_def_sum": 100 * (d_sr[h] + d_sr[a]),
            "to_diff": to_margin[h] - to_margin[a],
            "luck_diff": luck(h) - luck(a),
            # roster / coaching / QB changes (vs last season)
            "ret_off_diff": hc_[0] - ac_[0], "ret_def_diff": hc_[1] - ac_[1],
            "add_off_diff": hc_[2] - ac_[2], "add_def_diff": hc_[3] - ac_[3],
            "coach_tenure_diff": hc_[4] - ac_[4],
            "home_new_qb": hc_[5], "away_new_qb": ac_[5],
            "elo_stale_diff": ((elo[h] - 1500) * hc_[6] - (elo[a] - 1500) * ac_[6]) / 25,
            "epa_stale_diff": 100 * ((o_epa[h] - d_epa[h]) * hc_[6] - (o_epa[a] - d_epa[a]) * ac_[6]),
            "form_stale_sum": (off[h] - LEAGUE_PTS) * hc_[6] + (off[a] - LEAGUE_PTS) * ac_[6]
                              + (dfn[h] - LEAGUE_PTS) * hc_[6] + (dfn[a] - LEAGUE_PTS) * ac_[6],
            "ret_off_sum": hc_[0] + ac_[0], "stale_sum": hc_[6] + ac_[6],
            # independent model (nfelo) and market movement since the opening line
            "nfelo_diff": nfe[0], "nfelo_qb_diff": nfe[1], "spread_move": nfe[2],
            # referee crew tendencies (shrunk)
            "ref_total": ref_tot[ref] / ref_d if ref else 0.0,
            "ref_margin": ref_mar[ref] / ref_d if ref else 0.0,
            # this season only: average combined points in each team's games (no carry-over)
            "season_tot_sum": sum((season_rec[(r.season, t)][0] + season_rec[(r.season, t)][1]
                                   + season_tot_n * league_pts) / (season_rec[(r.season, t)][3] + season_tot_n)
                                  for t in (h, a)) - 2 * league_pts,
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
            "rain": r.rain, "snow": r.snow, "gusty": r.gusty,
            "wet_wind": (r.rain + r.snow) * r.wind,
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
        def alpha(base, t):
            if EARLY_K is None:
                return base
            return max(base, 1 / (season_rec[(r.season, t)][3] + EARLY_K))

        fa_h, fa_a = alpha(FORM_ALPHA, h), alpha(FORM_ALPHA, a)
        ea = {t: alpha(EPA_ALPHA, t) for t in (h, a)}
        off[h] += fa_h * (r.home_score - off[h]); dfn[h] += fa_h * (r.away_score - dfn[h])
        off[a] += fa_a * (r.away_score - off[a]); dfn[a] += fa_a * (r.home_score - dfn[a])
        league_pts += 0.01 * (r.total - league_pts)
        if ref and not np.isnan(r.total_line) and not np.isnan(r.spread_line):
            ref_tot[ref] += r.total - r.total_line
            ref_mar[ref] += res - r.spread_line
            ref_n[ref] += 1
        for t, opp, pts, opp_pts in ((h, a, r.home_score, r.away_score), (a, h, r.away_score, r.home_score)):
            rec = season_rec[(r.season, t)]
            rec[0] += pts; rec[1] += opp_pts; rec[2] += 1.0 if pts > opp_pts else (0.5 if pts == opp_pts else 0.0); rec[3] += 1
        ph, pa_ = plays.get((r.game_id, h)), plays.get((r.game_id, a))
        if ph and pa_:
            pre = {t: (o_epa[t], d_epa[t], o_sr[t], d_sr[t]) for t in (h, a)}
            for t, opp, mine, theirs in ((h, a, ph, pa_), (a, h, pa_, ph)):
                oe, de, os_, ds = pre[opp]
                o_epa[t] += ea[t] * ((mine[0] - de) - o_epa[t])
                d_epa[t] += ea[t] * ((theirs[0] - oe) - d_epa[t])
                o_sr[t] += ea[t] * ((mine[1] - LEAGUE_SR - ds) - o_sr[t])
                d_sr[t] += ea[t] * ((theirs[1] - LEAGUE_SR - os_) - d_sr[t])
                to_margin[t] += ea[t] * ((theirs[2] - mine[2]) - to_margin[t])
        resid = res - elo_d / 25
        for qb, sign in ((r.home_qb_id, 1), (r.away_qb_id, -1)):
            if isinstance(qb, str):
                qb_val[qb] = QB_DECAY * qb_val[qb] + sign * resid
                qb_n[qb] = QB_DECAY * qb_n[qb] + 1
                qb_starts[qb] += 1
        for t, hc in ((h, r.home_coach), (a, r.away_coach)):
            if isinstance(hc, str):
                coach[t] = hc
                coach_games[(t, hc)] += 1
        for qb, t in ((r.home_qb_id, h), (r.away_qb_id, a)):
            if isinstance(qb, str):
                qb_team_starts[(qb, t)] += 1
        if isinstance(r.home_qb_id, str):
            recent_qbs[h].append(r.home_qb_id)
        if isinstance(r.away_qb_id, str):
            recent_qbs[a].append(r.away_qb_id)

    return pd.DataFrame(rows)
