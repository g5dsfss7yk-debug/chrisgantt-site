"""Turn raw data into one row of pre-game features per game.

Every feature is computed only from information available before kickoff: ratings are
updated after a game is recorded as played. Features are grouped by *when* they are
known (see model.OPEN_FEATURES / CLOSE_FEATURES): when lines open early in the week,
or only on game day (final injury report, confirmed starters, forecast, line movement).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque

import numpy as np
import pandas as pd

from . import teams

ELO_K = 20
ELO_HFA = 48            # Elo points (~1.9 pts on the field)
ELO_REVERT = 1 / 3      # pull toward 1500 at each new season
FORM_ALPHA = 0.2        # EWMA weight of the latest game for points scored/allowed
EPA_ALPHA = 0.15        # EWMA weight of the latest game for play-level efficiency
SEASON_KEEP = 0.5       # share of last season's form/efficiency kept at a new season
LEAGUE_PTS = 22.5       # long-run points per team per game
LEAGUE_SR = 0.45        # long-run success rate per play
LEAGUE_EXP = 0.09       # explosive plays (20+ yd pass, 10+ yd run) per play
LEAGUE_SACK = 0.065     # sacks per dropback
LEAGUE_RZ = 0.56        # touchdowns per red-zone trip
LEAGUE_PACE = 37.5      # neutral-situation seconds per snap
LEAGUE_PLAYS = 61.0     # offensive snaps per team per game
LEAGUE_PASS = 0.55      # neutral-situation dropback rate
QB_DECAY = 0.95
QB_PRIOR = 6            # pseudo-starts shrinking a QB's value toward 0
PYTHAG_EXP = 2.37

# Probability an injured player misses the game, by final report status.
MISS_PROB = {"Out": 1.0, "Doubtful": 0.85, "Questionable": 0.25}
# Relative value of a full-time starter at each position (QBs are handled separately).
POS_WEIGHT = {
    "WR": 1.0, "TE": 0.7, "RB": 0.5, "HB": 0.5, "FB": 0.2,
    "T": 0.9, "G": 0.6, "C": 0.6, "OL": 0.7,
    "DE": 1.0, "DT": 0.6, "NT": 0.6, "DL": 0.8, "LB": 0.6, "ILB": 0.6, "OLB": 0.9,
    "CB": 1.0, "S": 0.7, "FS": 0.7, "SS": 0.7, "DB": 0.8,
}
# Position groups for injury clusters: skill, offensive line, pass rush, linebackers, secondary.
GROUP = {**dict.fromkeys(["WR", "TE", "RB", "HB", "FB"], 0), **dict.fromkeys(["T", "G", "C", "OL"], 1),
         **dict.fromkeys(["DE", "DT", "NT", "DL", "OLB"], 2), **dict.fromkeys(["LB", "ILB"], 3),
         **dict.fromkeys(["CB", "S", "FS", "SS", "DB"], 4)}
NO_INJURY = (0.0, 0.0, 0.0, 0.0, 0.0)
DEFAULT_CONTINUITY = (0.65, 0.65, 0.1, 0.1)

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_GUST = re.compile(r"gust\w*\s*(?:to|of|up to)?\s*(\d+)")


def _name_key(name: str) -> str:
    s = re.sub(r"[^a-z ]", "", str(name).lower().replace("-", " "))
    return " ".join(_SUFFIX.sub("", s).split())


# --- injuries -----------------------------------------------------------------
def injury_scores(injuries: pd.DataFrame, snaps: pd.DataFrame) -> dict:
    """{(season, week, franchise): burden by group (skill, o-line, pass rush, LB, secondary)}.

    burden = sum over injured non-QBs of P(miss) * position weight * recent snap share.
    Snap share uses only weeks before the report, so long absences already reflected in
    a team's ratings fade out.
    """
    if injuries.empty:
        return {}
    snaps = snaps.assign(pct=snaps[["offense_pct", "defense_pct"]].max(axis=1),
                         key=snaps["player"].map(_name_key), fr=snaps["team"].map(teams.franchise))
    hist = defaultdict(list)
    for r in snaps[["fr", "key", "season", "week", "pct"]].itertuples(index=False):
        hist[(r.fr, r.key)].append((r.season, r.week, r.pct))
    for v in hist.values():
        v.sort()

    def share(fr, key, season, week):
        rows = hist.get((fr, key))
        if not rows:
            return 0.25  # unknown player: assume a part-time contributor
        cur = [p for s, w, p in rows if s == season and w < week][-4:]
        if cur:
            return float(np.mean(cur))
        prev = [p for s, w, p in rows if s == season - 1]
        return float(np.mean(prev)) if prev else 0.25

    inj = injuries[injuries["report_status"].isin(MISS_PROB) & injuries["position"].isin(POS_WEIGHT)]
    if "date_modified" in inj:
        inj = inj.sort_values("date_modified")
    inj = inj.drop_duplicates(["season", "week", "team", "gsis_id"], keep="last")
    out = defaultdict(lambda: [0.0] * 5)
    for r in inj.itertuples(index=False):
        fr = teams.franchise(r.team)
        w = MISS_PROB[r.report_status] * POS_WEIGHT[r.position] * share(
            fr, _name_key(r.full_name), r.season, r.week)
        out[(r.season, r.week, fr)][GROUP[r.position]] += w
    return {k: tuple(v) for k, v in out.items()}


# --- roster continuity ---------------------------------------------------------
def roster_continuity(snaps: pd.DataFrame, rosters: pd.DataFrame) -> dict:
    """{(season, franchise): (returning_off, returning_def, added_off, added_def)}.

    returning = share of last season's offensive/defensive snaps played by players on
    the season-opening roster; added = last-season snaps (in team-seasons) those players
    played elsewhere. Low returning / high added = rebuilt team, stale ratings.
    """
    if snaps.empty or rosters.empty:
        return {}
    sn = snaps[snaps["game_type"] == "REG"].assign(
        fr=lambda d: d["team"].map(teams.franchise), key=lambda d: d["player"].map(_name_key))
    by = sn.groupby(["season", "fr", "pfr_player_id", "key"])[["offense_snaps", "defense_snaps"]].sum()
    by = by.reset_index()
    totals = by.groupby(["season", "fr"])[["offense_snaps", "defense_snaps"]].sum()
    ro = rosters.assign(fr=rosters["team"].map(teams.franchise), key=rosters["full_name"].map(_name_key))
    out = {}
    for season, rs in ro.groupby("season"):
        prev = by[by["season"] == season - 1]
        if prev.empty:
            continue
        tot, avg = totals.loc[season - 1], totals.loc[season - 1].mean()
        id_rows, name_rows = prev.set_index("pfr_player_id"), prev.set_index("key")
        for fr, team_r in rs.groupby("fr"):
            if fr not in tot.index:
                continue
            ids = set(team_r["pfr_id"].dropna())
            names = set(team_r.loc[team_r["pfr_id"].isna(), "key"])
            hit = pd.concat([id_rows[id_rows.index.isin(ids)], name_rows[name_rows.index.isin(names)]])
            own = hit[hit["fr"] == fr][["offense_snaps", "defense_snaps"]].sum()
            other = hit[hit["fr"] != fr][["offense_snaps", "defense_snaps"]].sum()
            t = tot.loc[fr]
            out[(season, fr)] = (own.offense_snaps / t.offense_snaps, own.defense_snaps / t.defense_snaps,
                                 other.offense_snaps / avg.offense_snaps, other.defense_snaps / avg.defense_snaps)
    return out


# --- weather ---------------------------------------------------------------------
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


def weather(g: pd.DataFrame, weather_text: pd.DataFrame | None, forecasts: dict | None) -> pd.DataFrame:
    """Observed weather for played games; forecast (else climatology) for upcoming ones."""
    g = g.copy()
    desc = {} if weather_text is None else dict(zip(weather_text["game_id"], weather_text["weather"]))
    parsed = [_precip(desc.get(i)) for i in g["game_id"]]
    g["rain"], g["snow"], g["gust"] = zip(*parsed) if parsed else ([], [], [])
    usual = g.dropna(subset=["roof"]).groupby("stadium_id")["roof"].agg(lambda s: s.mode().iat[0])
    g["roof"] = g["roof"].fillna(g["stadium_id"].map(usual)).fillna("outdoors")
    g["dome"] = g["roof"].isin(["dome", "closed"]).astype(int)
    g["month"] = g["gameday"].dt.month
    seen = g[(g["dome"] == 0) & g["temp"].notna()]
    clim = seen.groupby(["home_team", "month"])[["temp", "wind"]].median()
    month_clim = seen.groupby("month")[["temp", "wind"]].median()
    for col in ("temp", "wind"):
        fill = pd.Series([clim[col].get(i, np.nan) for i in zip(g["home_team"], g["month"])], index=g.index)
        g[col] = g[col].fillna(fill.fillna(g["month"].map(month_clim[col])))
    for key, f in (forecasts or {}).items():
        m = ((g["game_id"] == key) | (g["home_team"] == key)) & g["result"].isna()
        g.loc[m, ["temp", "wind"]] = [f["temp"], f["wind"]]
        g.loc[m, ["gust", "rain", "snow"]] = [f.get("gust", np.nan), f.get("rain", 0.0), f.get("snow", 0.0)]
    g["gust"] = g["gust"].fillna(g["wind"]).clip(lower=g["wind"])
    g.loc[g["dome"] == 1, ["temp", "wind", "gust", "rain", "snow"]] = [70, 0, 0, 0.0, 0.0]
    g["temp"], g["wind"] = g["temp"].fillna(60), g["wind"].fillna(8)
    g["cold"] = (45 - g["temp"]).clip(lower=0)
    g["heat"] = (g["temp"] - 85).clip(lower=0)
    g["high_wind"] = (g["wind"] - 10).clip(lower=0)
    g["gusty"] = (g["gust"] - 20).clip(lower=0)
    g["turf"] = (~g["surface"].fillna("grass").str.contains("grass")).astype(int)
    return g


# --- running team state ------------------------------------------------------------
class League:
    """Ratings and history that evolve game by game. Read before kickoff, update after."""

    def __init__(self):
        self.elo = defaultdict(lambda: 1500.0)
        self.off = defaultdict(lambda: LEAGUE_PTS)      # EWMA points scored
        self.dfn = defaultdict(lambda: LEAGUE_PTS)      # EWMA points allowed
        self.o_epa, self.d_epa = defaultdict(float), defaultdict(float)  # opponent-adjusted
        self.o_sr, self.d_sr = defaultdict(float), defaultdict(float)
        self.to_margin = defaultdict(float)             # EWMA takeaways - giveaways
        self.o_exp, self.d_exp = defaultdict(float), defaultdict(float)  # explosive-play rate, adjusted
        self.o_sack, self.d_sack = defaultdict(lambda: LEAGUE_SACK), defaultdict(lambda: LEAGUE_SACK)
        self.rz = {k: defaultdict(lambda: (LEAGUE_RZ * 3, 3.0)) for k in ("o", "d")}  # (TDs, trips)
        self.st = defaultdict(float)                    # EWMA net special-teams EPA per game
        self.fg = defaultdict(lambda: (0.85 * 4, 4.0))  # (made, attempts)
        self.pace = defaultdict(lambda: LEAGUE_PACE)    # neutral seconds per snap
        self.plays = defaultdict(lambda: LEAGUE_PLAYS)  # offensive snaps per game
        self.pass_rate = defaultdict(lambda: LEAGUE_PASS)  # neutral-situation dropback rate
        self.record = defaultdict(lambda: [0.0, 0.0, 0.0, 0])  # (season, team): pf, pa, wins, games
        self.league_pts = 2 * LEAGUE_PTS
        self.season_of = {}
        self.qb_val, self.qb_n, self.qb_starts = defaultdict(float), defaultdict(float), Counter()
        self.qb_team_starts = Counter()                 # (qb, team) -> starts for that team
        self.recent_qbs = defaultdict(lambda: deque(maxlen=8))
        self.coach, self.coach_games = {}, Counter()

    def new_season(self, t, season):
        if self.season_of.get(t, season) != season:
            self.elo[t] = 1500 + (self.elo[t] - 1500) * (1 - ELO_REVERT)
            self.off[t] = LEAGUE_PTS + (self.off[t] - LEAGUE_PTS) * SEASON_KEEP
            self.dfn[t] = LEAGUE_PTS + (self.dfn[t] - LEAGUE_PTS) * SEASON_KEEP
            for d in (self.o_epa, self.d_epa, self.o_sr, self.d_sr, self.o_exp, self.d_exp, self.st):
                d[t] *= SEASON_KEEP
            for d, base in ((self.o_sack, LEAGUE_SACK), (self.d_sack, LEAGUE_SACK), (self.pace, LEAGUE_PACE),
                            (self.plays, LEAGUE_PLAYS), (self.pass_rate, LEAGUE_PASS)):
                d[t] = base + (d[t] - base) * SEASON_KEEP
            self.to_margin[t] = 0.0
        self.season_of[t] = season

    def rz_rate(self, side, t):
        tds, trips = self.rz[side][t]
        return tds / trips

    def fg_rate(self, t):
        made, att = self.fg[t]
        return made / att

    def starter(self, t, qb):
        return qb if isinstance(qb, str) else (self.recent_qbs[t][-1] if self.recent_qbs[t] else None)

    def qb(self, t, qb):
        val = self.qb_val[qb] / (self.qb_n[qb] + QB_PRIOR) if qb else 0.0
        exp = math.log1p(min(self.qb_starts[qb], 50)) if qb else 0.0
        usual = Counter(self.recent_qbs[t]).most_common(1)
        backup = int(bool(usual) and usual[0][0] != qb and usual[0][1] >= 3)
        new = int(bool(qb) and self.qb_team_starts[(qb, t)] < 4)
        return val, exp, backup, new

    def luck(self, season, t):
        """Season win% above Pythagorean expectation, weighted by games played."""
        pf, pa, w, n = self.record[(season, t)]
        if n == 0 or pf + pa == 0:
            return 0.0
        return (w / n - pf ** PYTHAG_EXP / (pf ** PYTHAG_EXP + pa ** PYTHAG_EXP)) * min(n, 8) / 8

    def staleness(self, season, t, cont, coach_tenure, new_qb):
        """How much last season still drives this team's ratings, fading as games come in."""
        churn = (1 - (cont[0] + cont[1]) / 2) + 0.15 * (coach_tenure < 17) + 0.15 * new_qb
        return churn * 0.7 ** self.record[(season, t)][3]

    def update(self, r, h, a, elo_d, plays):
        res = r.result
        exp = 1 / (1 + 10 ** (-elo_d / 400))
        act = 1.0 if res > 0 else (0.5 if res == 0 else 0.0)
        mult = math.log(abs(res) + 1) * 2.2 / ((elo_d if res > 0 else -elo_d) * 0.001 + 2.2)
        self.elo[h] += ELO_K * mult * (act - exp)
        self.elo[a] -= ELO_K * mult * (act - exp)
        for t, pts, opp in ((h, r.home_score, r.away_score), (a, r.away_score, r.home_score)):
            self.off[t] += FORM_ALPHA * (pts - self.off[t])
            self.dfn[t] += FORM_ALPHA * (opp - self.dfn[t])
            rec = self.record[(r.season, t)]
            rec[0] += pts; rec[1] += opp; rec[3] += 1
            rec[2] += 1.0 if pts > opp else (0.5 if pts == opp else 0.0)
        self.league_pts += 0.01 * (r.total - self.league_pts)
        ph, pa = plays.get((r.game_id, h)), plays.get((r.game_id, a))
        if ph is not None and pa is not None:
            pre = {t: (self.o_epa[t], self.d_epa[t], self.o_sr[t], self.d_sr[t],
                       self.o_exp[t], self.d_exp[t]) for t in (h, a)}
            k = EPA_ALPHA
            for t, opp, me, th in ((h, a, ph, pa), (a, h, pa, ph)):
                oe, de, os_, ds, ox, dx = pre[opp]
                self.o_epa[t] += k * ((me.epa - de) - self.o_epa[t])
                self.d_epa[t] += k * ((th.epa - oe) - self.d_epa[t])
                self.o_sr[t] += k * ((me.sr - LEAGUE_SR - ds) - self.o_sr[t])
                self.d_sr[t] += k * ((th.sr - LEAGUE_SR - os_) - self.d_sr[t])
                self.to_margin[t] += k * ((th.giveaways - me.giveaways) - self.to_margin[t])
                self.o_exp[t] += k * ((me.explosive - LEAGUE_EXP - dx) - self.o_exp[t])
                self.d_exp[t] += k * ((th.explosive - LEAGUE_EXP - ox) - self.d_exp[t])
                if me.dropbacks > 0:
                    self.o_sack[t] += k * (me.sacks / me.dropbacks - self.o_sack[t])
                if th.dropbacks > 0:
                    self.d_sack[t] += k * (th.sacks / th.dropbacks - self.d_sack[t])
                for side, row in (("o", me), ("d", th)):
                    tds, trips = self.rz[side][t]
                    self.rz[side][t] = ((1 - k) * tds + row.rz_tds, (1 - k) * trips + row.rz_trips)
                self.st[t] += k * ((me.st_epa - th.st_epa) - self.st[t])
                made, att = self.fg[t]
                self.fg[t] = ((1 - k) * made + me.fg_made, (1 - k) * att + me.fg_att)
                if not np.isnan(me.sec_per_play):
                    self.pace[t] += k * (me.sec_per_play - self.pace[t])
                self.plays[t] += k * (me.plays - self.plays[t])
                if not np.isnan(me.neutral_pass):
                    self.pass_rate[t] += k * (me.neutral_pass - self.pass_rate[t])
        resid = res - elo_d / 25
        for qb, t, sign in ((r.home_qb_id, h, 1), (r.away_qb_id, a, -1)):
            if isinstance(qb, str):
                self.qb_val[qb] = QB_DECAY * self.qb_val[qb] + sign * resid
                self.qb_n[qb] = QB_DECAY * self.qb_n[qb] + 1
                self.qb_starts[qb] += 1
                self.qb_team_starts[(qb, t)] += 1
                self.recent_qbs[t].append(qb)
        for t, hc in ((h, r.home_coach), (a, r.away_coach)):
            if isinstance(hc, str):
                self.coach[t] = hc
                self.coach_games[(t, hc)] += 1


# --- builder -------------------------------------------------------------------------
def build(games: pd.DataFrame, *, injuries: dict, continuity: dict, pbp: pd.DataFrame,
          weather_text: pd.DataFrame | None, nfelo: pd.DataFrame | None,
          forecasts: dict | None = None) -> pd.DataFrame:
    g = games[games["game_type"].isin(["REG", "WC", "DIV", "CON", "SB"])].copy()
    g["gametime"] = g["gametime"].fillna("13:00")
    g = g.sort_values(["gameday", "gametime", "game_id"]).reset_index(drop=True)
    g = weather(g, weather_text, forecasts)

    plays = {(r.game_id, teams.franchise(r.team)): r for r in pbp.itertuples(index=False)}
    nf = {}
    for x in (nfelo.itertuples(index=False) if nfelo is not None else []):
        nf[(x.season, x.week, x.home_fr, x.away_fr)] = (
            (x.starting_nfelo_home - x.starting_nfelo_away) / 25,
            (x.home_538_qb_adj - x.away_538_qb_adj) / 25,
            -x.home_line_open)  # opening spread, + = home favored (games.csv convention)

    L = League()
    rows = []
    for r in g.itertuples(index=False):
        h, a = teams.franchise(r.home_team), teams.franchise(r.away_team)
        L.new_season(h, r.season)
        L.new_season(a, r.season)
        neutral = int(r.location == "Neutral")
        elo_d = L.elo[h] - L.elo[a] + (0 if neutral else ELO_HFA)
        hq, aq = L.starter(h, r.home_qb_id), L.starter(a, r.away_qb_id)
        hv, he, hb, hn = L.qb(h, hq)
        av, ae, ab, an = L.qb(a, aq)
        hi = injuries.get((r.season, r.week, h), NO_INJURY)
        ai = injuries.get((r.season, r.week, a), NO_INJURY)
        h_off_inj, a_off_inj = hi[0] + hi[1], ai[0] + ai[1]
        h_def_inj, a_def_inj = hi[2] + hi[3] + hi[4], ai[2] + ai[3] + ai[4]
        # Pass rush vs pass protection: each side's sack-rate edge, with injured blockers.
        h_rush_edge = L.d_sack[h] + L.o_sack[a]   # home rushers vs away line
        a_rush_edge = L.d_sack[a] + L.o_sack[h]
        hcont = continuity.get((r.season, h), DEFAULT_CONTINUITY)
        acont = continuity.get((r.season, a), DEFAULT_CONTINUITY)
        h_coach = r.home_coach if isinstance(r.home_coach, str) else L.coach.get(h)
        a_coach = r.away_coach if isinstance(r.away_coach, str) else L.coach.get(a)
        h_ten, a_ten = L.coach_games[(h, h_coach)], L.coach_games[(a, a_coach)]
        h_stale = L.staleness(r.season, h, hcont, h_ten, hn)
        a_stale = L.staleness(r.season, a, acont, a_ten, an)
        nfe = nf.get((r.season, r.week, h, a))
        away_mi = 0.0 if neutral else teams.miles(r.away_team, r.home_team)
        tz_shift = 0 if neutral else teams.tz(r.home_team) - teams.tz(r.away_team)
        early_body_clock = int(not neutral and int(str(r.gametime)[:2]) <= 13
                               and teams.tz(r.away_team) <= -7 and teams.tz(r.home_team) >= -6)
        outdoor_cold = r.cold * (1 - r.dome)
        h_net_epa, a_net_epa = L.o_epa[h] - L.d_epa[h], L.o_epa[a] - L.d_epa[a]
        h_rec, a_rec = L.record[(r.season, h)], L.record[(r.season, a)]

        def season_total(rec):  # this season's avg game total, shrunk to league average
            return (rec[0] + rec[1] + 3 * L.league_pts) / (rec[3] + 3) - L.league_pts

        rows.append({
            "game_id": r.game_id, "season": r.season, "week": r.week, "game_type": r.game_type,
            "gameday": r.gameday, "gametime": r.gametime,
            "home_team": r.home_team, "away_team": r.away_team,
            "home_qb": r.home_qb_name, "away_qb": r.away_qb_name,
            "home_score": r.home_score, "away_score": r.away_score,
            "result": r.result, "total": r.total,
            "spread_line": r.spread_line, "total_line": r.total_line,
            "spread_open": nfe[2] if nfe else np.nan,
            "home_moneyline": r.home_moneyline, "away_moneyline": r.away_moneyline,
            # strength
            "elo_diff": (L.elo[h] - L.elo[a]) / 25,
            "nfelo_diff": nfe[0] if nfe else (L.elo[h] - L.elo[a]) / 25,
            "nfelo_qb_diff": nfe[1] if nfe else 0.0,
            "form_diff": (L.off[h] - L.dfn[h]) - (L.off[a] - L.dfn[a]),
            "epa_diff": 100 * (h_net_epa - a_net_epa),
            "sr_diff": 100 * ((L.o_sr[h] - L.d_sr[h]) - (L.o_sr[a] - L.d_sr[a])),
            "to_diff": L.to_margin[h] - L.to_margin[a],
            "luck_diff": L.luck(r.season, h) - L.luck(r.season, a),
            # quarterbacks
            "qb_val_diff": hv - av, "qb_exp_diff": he - ae,
            "home_new_qb": hn, "away_new_qb": an,
            "home_backup_qb": hb, "away_backup_qb": ab,
            # roster / coaching change
            "ret_off_diff": hcont[0] - acont[0], "ret_def_diff": hcont[1] - acont[1],
            "add_off_diff": hcont[2] - acont[2], "add_def_diff": hcont[3] - acont[3],
            "coach_tenure_diff": math.log1p(h_ten) - math.log1p(a_ten),
            "elo_stale_diff": ((L.elo[h] - 1500) * h_stale - (L.elo[a] - 1500) * a_stale) / 25,
            "epa_stale_diff": 100 * (h_net_epa * h_stale - a_net_epa * a_stale),
            "stale_sum": h_stale + a_stale,
            # situation
            "home_field": 1 - neutral, "div_game": r.div_game,
            "rest_diff": float(np.clip(r.home_rest - r.away_rest, -7, 7)),
            "home_off_bye": int(r.home_rest >= 13), "away_off_bye": int(r.away_rest >= 13),
            "home_short_week": int(r.home_rest <= 5), "away_short_week": int(r.away_rest <= 5),
            "travel": away_mi / 1000, "away_tz_east": tz_shift, "body_clock_early": early_body_clock,
            # matchups and finishing (known at open)
            "explosive_diff": 100 * ((L.o_exp[h] - L.d_exp[h]) - (L.o_exp[a] - L.d_exp[a])),
            "rz_diff": (L.rz_rate("o", h) - L.rz_rate("d", h)) - (L.rz_rate("o", a) - L.rz_rate("d", a)),
            "st_diff": L.st[h] - L.st[a], "fg_diff": L.fg_rate(h) - L.fg_rate(a),
            "sack_matchup_diff": 100 * (h_rush_edge - a_rush_edge),
            # injuries (final report), by unit and as clusters (2+ starters missing in a unit)
            "inj_off_diff": h_off_inj - a_off_inj, "inj_def_diff": h_def_inj - a_def_inj,
            "inj_off_sum": h_off_inj + a_off_inj, "inj_def_sum": h_def_inj + a_def_inj,
            "ol_inj_diff": hi[1] - ai[1], "rush_inj_diff": hi[2] - ai[2], "sec_inj_diff": hi[4] - ai[4],
            "ol_cluster_diff": max(hi[1] - 1, 0) - max(ai[1] - 1, 0),
            "sec_cluster_diff": max(hi[4] - 1, 0) - max(ai[4] - 1, 0),
            "ol_exposed_diff": 100 * (hi[1] * L.d_sack[a] - ai[1] * L.d_sack[h]),
            "sec_inj_sum": hi[4] + ai[4], "rush_inj_sum": hi[2] + ai[2], "ol_inj_sum": hi[1] + ai[1],
            "def_cluster_sum": sum(max(x[i] - 1, 0) for x in (hi, ai) for i in (2, 3, 4)),
            # pace and style (totals)
            "pace_sum": L.pace[h] + L.pace[a], "plays_sum": L.plays[h] + L.plays[a],
            "pass_rate_sum": L.pass_rate[h] + L.pass_rate[a],
            "explosive_sum": 100 * (L.o_exp[h] + L.o_exp[a] + L.d_exp[h] + L.d_exp[a]),
            "rz_sum": L.rz_rate("o", h) + L.rz_rate("o", a) + L.rz_rate("d", h) + L.rz_rate("d", a),
            # scoring environment
            "off_sum": L.off[h] + L.off[a], "def_sum": L.dfn[h] + L.dfn[a], "league_pts": L.league_pts,
            "epa_off_sum": 100 * (L.o_epa[h] + L.o_epa[a]), "epa_def_sum": 100 * (L.d_epa[h] + L.d_epa[a]),
            "sr_off_sum": 100 * (L.o_sr[h] + L.o_sr[a]), "sr_def_sum": 100 * (L.d_sr[h] + L.d_sr[a]),
            "season_tot_sum": season_total(h_rec) + season_total(a_rec),
            # weather
            "dome": r.dome, "temp": r.temp, "wind": r.wind, "gust": r.gust,
            "cold": r.cold, "heat": r.heat, "high_wind": r.high_wind, "gusty": r.gusty,
            "rain": r.rain, "snow": r.snow, "wet_wind": (r.rain + r.snow) * r.wind, "turf": r.turf,
            "away_dome_team_cold": outdoor_cold * int(teams.is_dome_team(a, r.season)),
            "home_dome_team_cold": outdoor_cold * int(teams.is_dome_team(h, r.season)),
        })
        if not np.isnan(r.result):
            L.update(r, h, a, elo_d, plays)
    df = pd.DataFrame(rows)
    df["spread_move"] = (df["spread_line"] - df["spread_open"]).fillna(0.0)
    return df
