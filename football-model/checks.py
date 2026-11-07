"""Pre-bet checks printed under every game on the NFL and college cards.

Each card game gets the same checklist: QB (listed, depth chart, last starter, injury
report), injuries to regulars, recent form and record against the spread, rest, weather
and field, and the line (opener / market vs yours). Anything the data could not confirm is
collected and printed as NOT VERIFIED at the end of the card, so a skipped check is visible.
"""
from __future__ import annotations

import pandas as pd


class Unverified(list):
    def add(self, game: str, what: str):
        self.append(f"{game}: {what}")

    def show(self):
        print("\nNOT VERIFIED (check before betting):")
        if not self:
            print("  nothing: every check above came from current data")
        for x in self:
            print(f"  - {x}")


def form(past: pd.DataFrame, team: str, line_col: str, n: int = 3) -> tuple[str, str]:
    """('W-L, ATS W-L', 'last n games') for a team from completed games (home-margin result,
    line = home team's points favored)."""
    mine = past[(past["home_team"] == team) | (past["away_team"] == team)].sort_values("gameday")
    w = l = cw = cl = 0
    last = []
    for x in mine.itertuples(index=False):
        home = x.home_team == team
        m = x.result if home else -x.result
        w, l = w + (m > 0), l + (m < 0)
        ats = ""
        ln = getattr(x, line_col)
        if pd.notna(ln):
            c = (x.result - ln) * (1 if home else -1)
            cw, cl = cw + (c > 0), cl + (c < 0)
            ats = "covered" if c > 0 else ("push" if c == 0 else "no cover")
        opp = x.away_team if home else x.home_team
        res = "W" if m > 0 else ("L" if m < 0 else "T")
        last.append(f"{'vs' if home else '@'} {opp} {res} by {abs(m):.0f}" + (f" ({ats})" if ats else ""))
    return f"{w}-{l}, ATS {cw}-{cl}", "; ".join(last[-n:]) or "no games yet"


def weather_text(w: dict | None, dome: bool, surface: str | None) -> str:
    field = f", {surface}" if surface else ""
    if dome:
        return f"dome / closed roof{field}"
    if not w or pd.isna(w.get("temp")):
        return f"NO FORECAST{field}"
    rain = w.get("precip_prob")
    wet = f", precip {rain:.0f}% ({w.get('precip_in', 0):.2f} in)" if pd.notna(rain) and rain >= 20 else ""
    snow = f", snow {w['snow_in']:.1f} in" if w.get("snow_in", 0) and w["snow_in"] > 0 else ""
    return f"{w['temp']:.0f}F, wind {w['wind']:.0f} mph (gusts {w.get('gust', 0):.0f}){wet}{snow}{field}"


STALE_HOURS = 6  # a forecast older than this is listed as NOT VERIFIED
RAIN_RISK = 35   # precipitation chance (%) that flags passing/receiving overs, even with ~0 inches forecast


def forecast_age(w: dict | None) -> float | None:
    """Hours since the forecast was fetched."""
    if not w or not isinstance(w.get("fetched_at"), str):
        return None
    t = pd.Timestamp(w["fetched_at"].replace("Z", "+00:00"))
    return (pd.Timestamp.now(tz="UTC") - t).total_seconds() / 3600


_ESPN: dict = {}
WET_WORDS = ("rain", "shower", "storm", "drizzle", "snow", "sleet", "flurr")


def espn_conditions(league: str, event_id, day) -> str | None:
    """ESPN's game-day conditions for one game (e.g. "Thunderstorms 64F"), a second weather source
    for when the hourly forecast API is down or rate limited. league: "nfl" or "college-football"."""
    if event_id is None or pd.isna(event_id):
        return None
    key = (league, f"{pd.Timestamp(day):%Y%m%d}")
    if key not in _ESPN:
        import json
        import urllib.request
        url = (f"https://site.api.espn.com/apis/site/v2/sports/football/{league}/scoreboard"
               f"?dates={key[1]}&limit=400" + ("&groups=80" if league == "college-football" else ""))
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                events = json.load(r).get("events", [])
        except (OSError, ValueError):
            events = []
        def cond(w):
            # the condition text is usually displayValue, but some games carry a code there and the
            # text in conditionId
            txt = [str(w.get(k) or "") for k in ("displayValue", "conditionId")]
            txt = next((t for t in txt if t and not t.isdigit()), "")
            return f"{txt} {w.get('temperature', '')}F".strip()
        _ESPN[key] = {e["id"]: cond(e["weather"]) for e in events if e.get("weather")}
    return _ESPN[key].get(str(int(float(event_id))))


def weather_check(label: str, w: dict | None, dome: bool, surface: str | None, unverified,
                  espn: str | None = None) -> str:
    """Weather line with the forecast's age; a missing or stale forecast goes on the NOT VERIFIED list
    unless ESPN's game-day conditions are there to cover it. Rain, storms or snow in either source
    raise the rain-risk warning."""
    text = weather_text(w, dome, surface)
    if dome:
        return text
    if espn:
        text += f"  ESPN: {espn}"
    wet_espn = bool(espn) and any(k in espn.lower() for k in WET_WORDS)
    age = forecast_age(w)
    if age is None and not espn:
        unverified.add(label, "weather (no forecast: run the weather job)")
    elif age is not None and age > STALE_HOURS and not espn:
        unverified.add(label, f"weather (forecast is {age:.0f} hours old: run the weather job and rerun)")
    p = w.get("precip_prob") if w else None
    if (p is not None and pd.notna(p) and p >= RAIN_RISK) or ((w or {}).get("snow_in") or 0) > 0 or wet_espn:
        why = f"ESPN: {espn}" if wet_espn else f"{p:.0f}% chance"
        unverified.add(label, f"RAIN/SNOW RISK ({why}): avoid QB passing and receiving overs; in rain "
                              "QBs threw 19-26 yds below their norm and 200+ fell from 66% to 51% (2020-26)")
        text += "  ** RAIN RISK: avoid passing/receiving overs **"
    return text if age is None else f"{text}  (forecast {age:.0f}h old)"


# --- NFL --------------------------------------------------------------------------------

class NFLChecks:
    """Loads the season's depth chart, injury report and snaps once for the whole card."""

    def __init__(self, season: int, week: int, refresh: bool = False):
        from nflmodel import data, lineups
        self.season, self.week = season, week
        self.lineups = lineups
        self.depth = lineups.load_depth(season, refresh)
        self.depth_day = str(self.depth["dt"].max())[:10]
        inj = data.load_injuries([season], refresh)
        self.inj = inj[inj["week"] == week]
        self.games = data.load_games(refresh)
        self.forecasts = {f.game_id: f._asdict() for f in data.load_forecasts().itertuples(index=False)}
        self._reports = {}

    def _report(self, team):
        if team not in self._reports:
            try:
                self._reports[team] = self.lineups.report(team, self.season, self.week)
            except Exception as e:  # never lose the card over a lineup problem
                self._reports[team] = e
        return self._reports[team]

    def _status(self, team, name):
        r = self.inj[(self.inj["team"] == team) & (self.inj["full_name"].str.lower() == str(name).lower())]
        if r.empty:
            return "not on injury report"
        x = r.iloc[-1]
        game = x["report_status"] if pd.notna(x["report_status"]) else "no game status yet"
        prac = x["practice_status"] if pd.notna(x["practice_status"]) else ""
        hurt = x["report_primary_injury"] if pd.notna(x["report_primary_injury"]) else x["practice_primary_injury"]
        return f"{game}" + (f" ({hurt})" if pd.notna(hurt) else "") + (f", practice: {prac}" if prac else "")

    def show(self, df: pd.DataFrame, g, last_qb: dict, confirmed: dict, opener: float, yours: float,
             unverified: Unverified):
        label = f"{g.away_team} @ {g.home_team}"
        past = df[(df["season"] == g.season) & df["result"].notna() & (df["gameday"] < g.gameday)]
        prev = df[df["result"].notna() & (df["gameday"] < g.gameday)].sort_values("gameday")
        for side in ("away", "home"):
            team = getattr(g, f"{side}_team")
            rec, last = form(past, team, "spread_line")
            mine = prev[(prev["home_team"] == team) | (prev["away_team"] == team)]
            rest = (g.gameday - mine["gameday"].max()).days if len(mine) else None
            tags = [t for t, on in (("off bye", getattr(g, f"{side}_off_bye", 0)),
                                    ("short week", getattr(g, f"{side}_short_week", 0))) if on]
            rest_txt = f"rest {rest} days" + (f" ({', '.join(tags)})" if tags else "") if rest is not None else ""
            print(f"   {team}: {rec}; {rest_txt}")
            print(f"      last 3: {last}")

            # QB: listed starter vs depth chart vs last starter vs injury report
            listed = getattr(g, f"{side}_qb")
            dq = self.depth[(self.depth["team"] == team) & (self.depth["pos_abb"] == "QB")].sort_values("pos_rank")
            qb1 = dq["player_name"].iloc[0] if len(dq) else None
            notes = []
            if team in confirmed:
                notes.append("starter set by --qb or depth chart + last start")
            else:
                if qb1 and self.lineups._norm(pd.Series([qb1]))[0] != self.lineups._norm(pd.Series([str(listed)]))[0]:
                    notes.append(f"depth chart ({self.depth_day}) has {qb1}")
                if team in last_qb and self.lineups._norm(pd.Series([str(last_qb[team])]))[0] != \
                        self.lineups._norm(pd.Series([str(listed)]))[0]:
                    notes.append(f"{last_qb[team]} started last game")
            st = self._status(team, listed)
            if st != "not on injury report":
                notes.append(f"injury report: {st}")
            print(f"      QB {listed}" + (f"  [{'; '.join(notes)}]" if notes else ""))
            if team not in confirmed and any(not n.startswith("injury report: not") for n in notes):
                unverified.add(label, f"{team} starting QB ({listed}) - confirm with news, rerun with --qb {team}=\"Name\"")

            # Injuries to regulars (>= half the snaps the last two games)
            r = self._report(team)
            if isinstance(r, Exception):
                print(f"      injuries: could not load ({r})")
                unverified.add(label, f"{team} injuries (lineup data failed)")
                continue
            miss = r["missing"]
            if len(miss):
                txt = ", ".join(f"{m.player} {m.position} ({m.status})" for m in miss.head(8).itertuples(index=False))
                print(f"      missing regulars: {txt}")
            q = [n for n in r["questionable"]]
            dnp = self.inj[(self.inj["team"] == team) & self.inj["report_status"].isna()
                           & self.inj["practice_status"].fillna("").str.contains("Did Not", case=False)]
            if q:
                print(f"      questionable: {', '.join(q[:8])}")
            if len(dnp):
                print(f"      did not practice (no game status yet): {', '.join(dnp['full_name'].head(8))}")
            if not len(miss) and not q and not len(dnp):
                print("      injuries: no regulars listed")
            if self.week_status_pending(team):
                unverified.add(label, f"{team} injury report has no game statuses yet (final report comes 2 days before kickoff)")

        raw = self.games.set_index("game_id")
        roof = raw.at[g.game_id, "roof"] if g.game_id in raw.index else None
        surface = raw.at[g.game_id, "surface"] if g.game_id in raw.index else None
        dome = roof in ("dome", "closed")
        w = self.forecasts.get(g.game_id)
        espn = espn_conditions("nfl", raw.at[g.game_id, "espn"], g.gameday) if g.game_id in raw.index else None
        print(f"   weather: {weather_check(label, w, dome, surface if isinstance(surface, str) else None, unverified, espn)}")
        if pd.notna(opener):
            moved = "" if opener == yours else f", yours {g.home_team} {-yours:+.1f}"
            print(f"   line: opened {g.home_team} {-opener:+.1f}{moved}")

    def brief(self, g, unverified: "Unverified"):
        """QB, injuries and weather for one game from the raw schedule row (used by props)."""
        label = f"{g.away_team} @ {g.home_team}"
        print(f"{label}  {g.gameday:%a %m/%d} {g.gametime} ET")
        for team, qb in ((g.away_team, g.away_qb_name), (g.home_team, g.home_qb_name)):
            st = self._status(team, qb)
            print(f"   {team} QB {qb}" + ("" if st == "not on injury report" else f"  [injury report: {st}]"))
            r = self._report(team)
            if isinstance(r, Exception):
                unverified.add(label, f"{team} injuries (lineup data failed)")
                continue
            out = self.inj[(self.inj["team"] == team) & self.inj["report_status"].isin(["Out", "Doubtful", "Questionable"])]
            if len(out):
                print("      " + ", ".join(f"{x.full_name} {x.position} {x.report_status}" for x in out.itertuples(index=False)))
            if self.week_status_pending(team):
                unverified.add(label, f"{team} injury report has no game statuses yet")
        dome = g.roof in ("dome", "closed")
        surface = g.surface if isinstance(g.surface, str) else None
        espn = espn_conditions("nfl", getattr(g, "espn", None), g.gameday)
        print(f"   weather: {weather_check(label, self.forecasts.get(g.game_id), dome, surface, unverified, espn)}")

    def week_status_pending(self, team) -> bool:
        t = self.inj[self.inj["team"] == team]
        return len(t) > 0 and t["report_status"].isna().all()


# --- college ----------------------------------------------------------------------------

def cfb_show(df: pd.DataFrame, g, ranks: pd.DataFrame, forecasts: dict, unverified: Unverified):
    label = f"{g.away_team} @ {g.home_team}"
    n = len(ranks)
    past = df[(df["season"] == g.season) & df["result"].notna() & (df["gameday"] < g.gameday)]
    for side in ("away", "home"):
        team = getattr(g, f"{side}_team")
        rec, last = form(past, team, "spread_close")
        if team in ranks.index:
            rk = lambda col, asc=False: int(ranks[col].rank(ascending=asc)[team])
            rank_txt = f"power #{rk('off_pts')}/{n}, offense EPA #{rk('off_epa')}, defense EPA #{rk('def_epa', True)}"
        else:
            rank_txt = "FCS"
        qb = getattr(g, f"{side}_qb")
        qbc = " (QB CHANGED last game)" if getattr(g, f"{side}_qb_change") else ""
        print(f"   {team}: {rec}; {rank_txt}; rest {getattr(g, f'{side}_rest'):.0f} days; QB {qb}{qbc}")
        print(f"      last 3: {last}")
        roster = _roster_text(team, g.season)
        if roster:
            print(f"      roster: {roster}")
        if qbc:
            unverified.add(label, f"{team} starting QB (changed last game) - check news")
    w = forecasts.get(f"cfb_{g.game_id}")
    surface = None if not w or pd.isna(w.get("grass")) else ("grass" if w["grass"] else "turf")
    espn = espn_conditions("college-football", g.game_id, g.gameday)
    print(f"   weather: {weather_check(label, w, bool(w and w.get('dome')), surface, unverified, espn)}")
    unverified.add(label, "injuries (no free college injury report: check team news)")


_ROSTER = {}


def _roster_text(team: str, season: int) -> str:
    """Talent rank, returning production, portal and coach (CollegeFootballData; blank without it)."""
    if season not in _ROSTER:
        from cfbmodel import cfbd
        ts = cfbd.team_seasons(season, season)
        ts = ts[ts["season"] == season].set_index("team")
        ts["talent_rank"] = ts["talent"].rank(ascending=False)
        _ROSTER[season] = ts
    ts = _ROSTER[season]
    if team not in ts.index:
        return ""
    r = ts.loc[team]
    bits = []
    if pd.notna(r["talent"]):
        bits.append(f"talent #{int(r['talent_rank'])}")
    if pd.notna(r["returning"]):
        bits.append(f"{r['returning']:.0%} of last year's offense back")
    if pd.notna(r["portal_net"]):
        bits.append(f"portal net {r['portal_net']:+.1f}")
    if r.get("new_coach") == 1:
        bits.append("NEW HEAD COACH")
    return ", ".join(bits)


def latest_ratings(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Each FBS team's most recent pregame ratings this season (for ranks)."""
    d = df[df["season"] == season].sort_values("gameday")
    out = {}
    for g in d.itertuples(index=False):
        for side in ("home", "away"):
            if not getattr(g, f"{side}_fcs"):
                out[getattr(g, f"{side}_team")] = {k: getattr(g, f"{side}_{k}") for k in
                                                   ("off_pts", "off_epa", "def_epa")}
    return pd.DataFrame(out).T
