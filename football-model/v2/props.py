"""V2 player props, built from scratch (Nov 15 2026). No code from nflmodel/props.py.

For each stat a gradient-boosting model predicts the player's number from pre-game inputs only
(his exponentially weighted recent games, role, team implied points and spread). The chance of
reaching a ladder rung comes from the actual outcomes of past player-games with similar
predictions (out-of-fold by season), so it is the rate at which such players really got there.
Test: fit on 2015-2022, check 2023-26 (v2/test_props.py).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import re
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from nflmodel import data, teams

RAW = ["carries", "targets", "receptions", "rushing_yards", "receiving_yards", "attempts", "completions",
       "passing_yards", "passing_tds", "rushing_tds", "receiving_tds", "target_share", "air_yards_share", "snap_pct"]
def _rush(d): return d["rushing_yards"]
def _rec(d): return d["receiving_yards"]
def _pass(d): return d["passing_yards"]
def _recp(d): return d["receptions"]
def _rr(d): return d["rushing_yards"] + d["receiving_yards"]
def _ptd(d): return d["passing_tds"]
def _td(d): return d["rushing_tds"] + d["receiving_tds"]


STATS = {  # market -> (positions, how to compute)
    "rushing_yards": (("RB", "QB", "WR"), _rush),
    "receiving_yards": (("WR", "TE", "RB"), _rec),
    "passing_yards": (("QB",), _pass),
    "receptions": (("WR", "TE", "RB"), _recp),
    "rush_rec_yards": (("RB", "WR", "TE"), _rr),
    "passing_tds": (("QB",), _ptd),
    "anytime_td": (("RB", "WR", "TE", "QB"), _td),
}
HL = 4
COUNTS = {"receptions", "passing_tds", "anytime_td"}
BINS = 25
# Nov 23: receptions chance from the model's own number plus how far off similar players were
# (like yards), not from the raw outcomes of a wide group - the old way put high-volume receivers
# in one big top group and under-rated them (7+ catches: said 41%, hit 50%). v2/test_receptions.py
RESID_COUNTS = set()          # tried for receptions Nov 23: worse (v2/test_receptions.py)
NEAR = {"receptions": 500}    # market -> K: chance from the K past players with the CLOSEST projections (ON Nov 23)


def load() -> pd.DataFrame:
    s = pd.concat([pd.read_csv(data.RAW / "stats_player" / f"{y}.csv", low_memory=False)
                   for y in range(2013, data.current_season() + 1)], ignore_index=True)
    s = s[s["position"].isin(["QB", "RB", "WR", "TE"]) & s["season_type"].isin(["REG", "POST"])]
    s["team"] = s["team"].map(teams.franchise)
    g = data.load_games()
    g["home_fr"], g["away_fr"] = g["home_team"].map(teams.franchise), g["away_team"].map(teams.franchise)
    side = pd.concat([
        g.assign(team=g.home_fr, opp=g.away_fr, spread_for=g.spread_line, pts=g.total_line / 2 + g.spread_line / 2, home=1),
        g.assign(team=g.away_fr, opp=g.home_fr, spread_for=-g.spread_line, pts=g.total_line / 2 - g.spread_line / 2, home=0),
    ])[["game_id", "team", "opp", "spread_for", "pts", "home", "gameday"]]
    s = _with_snaps(s)
    s = s.merge(side, on=["game_id", "team"], how="left", suffixes=("", "_g"))
    for c in ("opp", "spread_for", "pts", "home", "gameday"):
        s[c] = s[c].fillna(s.pop(f"{c}_g")) if f"{c}_g" in s else s[c]
    for c in RAW + ["snap_pct"]:
        s[c] = s[c].fillna(0)
    return s.sort_values(["player_id", "gameday"]).reset_index(drop=True)


def _key(n):
    import unicodedata
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'\-]", "", n)
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", n).strip()


def _with_snaps(s):
    """Every game a player was on the field on offense counts, even with no stats (the stats
    file has no row for a player who played but recorded nothing - leaving those out makes
    every chance too high)."""
    sn = pd.concat([pd.read_csv(data.RAW / "snap_counts" / f"{y}.csv") for y in range(2013, data.current_season() + 1)
                    if (data.RAW / "snap_counts" / f"{y}.csv").exists()], ignore_index=True)
    sn = sn[(sn["offense_snaps"] >= 1) & sn["position"].isin(["QB", "RB", "WR", "TE", "FB"])]
    sn["team"] = sn["team"].map(teams.franchise)
    sn["k"] = sn["player"].map(_key)
    s["k"] = s["player_display_name"].map(_key)
    ids = s.drop_duplicates(["k", "team", "season"])[["k", "team", "season", "player_id", "player_display_name", "position"]]
    sn = sn.merge(ids, on=["k", "team", "season"], how="left", suffixes=("_sn", ""))
    sn["player_id"] = sn["player_id"].fillna("pfr:" + sn["pfr_player_id"].astype(str))
    sn["player_display_name"] = sn["player_display_name"].fillna(sn["player"])
    sn["position"] = sn["position"].fillna(sn["position_sn"]).replace({"FB": "RB"})
    sn = sn.rename(columns={"offense_pct": "snap_pct"})[["game_id", "team", "season", "week", "player_id",
                                                         "player_display_name", "position", "snap_pct"]]
    s = s.merge(sn[["game_id", "player_id", "snap_pct"]], on=["game_id", "player_id"], how="left")
    extra = sn.merge(s[["game_id", "player_id"]], on=["game_id", "player_id"], how="left", indicator=True)
    extra = extra[extra["_merge"] == "left_only"].drop(columns="_merge").assign(season_type="REG")
    return pd.concat([s, extra], ignore_index=True)


DEF = ["d_rush", "d_rec_wr", "d_rec_te", "d_rec_rb", "d_pass", "d_td", "d_recp_wr", "d_recp_te", "d_recp_rb", "d_pass_td"]
STAR = ["rushing_yards", "receiving_yards", "passing_yards", "receptions", "tds", "targets", "carries"]
DEF_HL, STAR_HL = 6, 16


def defense_games(s: pd.DataFrame) -> pd.DataFrame:
    """What each defense allowed in each game (all players it faced), by position group."""
    x = s.assign(tds=s["rushing_tds"] + s["receiving_tds"])
    pos = lambda p: x["position"] == p
    t = pd.DataFrame({
        "game_id": x["game_id"], "defense": x["opp"], "gameday": x["gameday"], "season": x["season"],
        "d_rush": x["rushing_yards"], "d_pass": x["passing_yards"], "d_td": x["tds"], "d_pass_td": x["passing_tds"],
        **{f"d_rec_{p.lower()}": x["receiving_yards"].where(pos(p), 0) for p in ("WR", "TE", "RB")},
        **{f"d_recp_{p.lower()}": x["receptions"].where(pos(p), 0) for p in ("WR", "TE", "RB")},
    })
    return t.groupby(["game_id", "defense", "gameday", "season"], as_index=False)[DEF].sum().sort_values("gameday")


def defense_form(s: pd.DataFrame, include_last: bool) -> pd.DataFrame:
    """Each defense's weighted recent average allowed: before each game (include_last=False) or
    going into its next game (True)."""
    t = defense_games(s)
    g = t.groupby("defense")
    if include_last:
        return g[DEF].agg(lambda x: x.ewm(halflife=DEF_HL).mean().iloc[-1]).add_prefix("opp_").reset_index()
    for c in DEF:
        t[f"opp_{c}"] = g[c].transform(lambda x: x.shift().ewm(halflife=DEF_HL, min_periods=1).mean())
    return t[["game_id", "defense"] + [f"opp_{c}" for c in DEF]]


PRESS_HL = 6


def pressure_form(include_last: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """QB pressure from play-by-play: (sacks + QB hits) per dropback. For each defense, the rate it
    GENERATES; for each offense, the rate its line ALLOWS. Weighted recent games, half-life 6."""
    t = data.load_team_pbp(range(2013, data.current_season() + 1))
    t["team"] = t["team"].map(teams.franchise)
    g = data.load_games()[["game_id", "gameday", "home_team", "away_team"]]
    t = t.merge(g, on="game_id")
    t["defense"] = np.where(t["team"] == t["home_team"].map(teams.franchise), t["away_team"], t["home_team"])
    t["defense"] = t["defense"].map(teams.franchise)
    t["rate"] = (t["sacks"] + t["qb_hits"]) / t["dropbacks"].clip(lower=1)
    t = t.sort_values("gameday")
    out = []
    for who, name in (("defense", "opp_pressure"), ("team", "own_pressure_allowed")):
        gg = t.groupby(who)["rate"]
        if include_last:
            out.append(gg.agg(lambda x: x.ewm(halflife=PRESS_HL).mean().iloc[-1]).rename(name).reset_index())
        else:
            out.append(t[["game_id", who]].assign(**{name: gg.transform(lambda x: x.shift().ewm(halflife=PRESS_HL, min_periods=1).mean())}))
    return out[0], out[1]


def history(s: pd.DataFrame) -> pd.DataFrame:
    """Pre-game features: EW means of earlier games only (shifted)."""
    g = s.groupby("player_id")
    for c in RAW:
        s[f"ew_{c}"] = g[c].transform(lambda x: x.shift().ewm(halflife=HL, min_periods=1).mean())
        s[f"last_{c}"] = g[c].shift()
    s["n_games"] = g.cumcount()
    s["tds"] = s["rushing_tds"] + s["receiving_tds"]
    s["ew_tds"] = g["tds"].transform(lambda x: x.shift().ewm(halflife=8, min_periods=1).mean())
    for c in STAR:   # long-run level ("star power"): career average with a 16-game half-life
        s[f"lr_{c}"] = g[c].transform(lambda x: x.shift().ewm(halflife=STAR_HL, min_periods=1).mean())
        s[f"max_{c}"] = g[c].transform(lambda x: x.shift().rolling(16, min_periods=1).quantile(0.8))
    s["td_game"] = (s["tds"] >= 1).astype(float)
    for c in ROBUST:   # median of the last 8 games: one 150-yard game moves it little
        s[f"med8_{c}"] = g[c].transform(lambda x: x.shift().rolling(8, min_periods=1).median())
    for n in (8, 16):  # share of games with a TD: four TDs in one game count once
        s[f"td_rate{n}"] = g["td_game"].transform(lambda x: x.shift().rolling(n, min_periods=1).mean())
    s = s.merge(vacated(s), on=["game_id", "team"], how="left")
    s = _vac_pos(s)
    s = s.merge(defense_form(s, False), left_on=["game_id", "opp"], right_on=["game_id", "defense"], how="left")
    s = s.drop(columns="defense")
    dp, op = pressure_form(False)
    s = s.merge(dp, left_on=["game_id", "opp"], right_on=["game_id", "defense"], how="left").drop(columns="defense")
    s = s.merge(op.rename(columns={"team": "team_p"}), left_on=["game_id", "team"], right_on=["game_id", "team_p"],
                how="left").drop(columns="team_p")
    return s


def next_game(s: pd.DataFrame) -> pd.DataFrame:
    """Features for each player's NEXT game (EW means including his latest game)."""
    s = s.copy()
    s["tds"] = s["rushing_tds"] + s["receiving_tds"]
    g = s.groupby("player_id")
    out = g.tail(1)[["player_id", "player_display_name", "position", "team", "gameday", "season"]].set_index("player_id")
    for c in RAW:
        out[f"ew_{c}"] = g[c].apply(lambda x: x.ewm(halflife=HL).mean().iloc[-1])
        out[f"last_{c}"] = g[c].last()
    out["ew_tds"] = g["tds"].apply(lambda x: x.ewm(halflife=8).mean().iloc[-1])
    out["n_games"] = g.size()
    for c in STAR:
        out[f"lr_{c}"] = g[c].apply(lambda x: x.ewm(halflife=STAR_HL).mean().iloc[-1])
        out[f"max_{c}"] = g[c].apply(lambda x: x.tail(16).quantile(0.8))
    for c in ROBUST:
        out[f"med8_{c}"] = g[c].apply(lambda x: x.tail(8).median())
    for n in (8, 16):
        out[f"td_rate{n}"] = g["tds"].apply(lambda x: (x.tail(n) >= 1).mean())
    return out.reset_index()


GROUP = {"WR": "WR", "TE": "TE", "RB": "RB", "QB": "QB"}


def _post_ew(s: pd.DataFrame) -> pd.DataFrame:
    """Each player's weighted targets/carries AFTER each game (what he takes into his next game)."""
    g = s.groupby("player_id")
    p = s[["player_id", "team", "position", "gameday"]].copy()
    for c in ("targets", "carries"):
        p[f"post_{c}"] = g[c].transform(lambda x: x.ewm(halflife=HL).mean())
    return p


def vacated(s: pd.DataFrame, out: pd.DataFrame | None = None, games: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per (game_id, team): weighted recent targets and carries of teammates listed Out/Doubtful that
    week who played in one of the team's last 3 games - the work someone else has to take.
    `out` (season, week, team, player_id) defaults to the official injury reports; `games`
    (game_id, team, season, week, gameday) defaults to every game in s."""
    if out is None:
        inj = pd.concat([pd.read_csv(f, low_memory=False) for f in sorted((data.RAW / "injuries").glob("*.csv"))])
        inj = inj[inj.report_status.isin(["Out", "Doubtful"])]
        out = inj.assign(team=inj.team.map(teams.franchise)).rename(columns={"gsis_id": "player_id"})[
            ["season", "week", "team", "player_id"]].drop_duplicates()
    if games is None:
        games = s[["game_id", "team", "season", "week", "gameday"]].drop_duplicates(["game_id", "team"])
    post = _post_ew(s).dropna(subset=["gameday"])
    games = games.dropna(subset=["gameday"])
    tg = s[["team", "gameday"]].dropna().drop_duplicates().sort_values("gameday")
    tg["k"] = tg.groupby("team").cumcount()
    games = games.merge(out, on=["season", "week", "team"])
    last = post.sort_values("gameday")
    m = pd.merge_asof(games.sort_values("gameday"), last.rename(columns={"gameday": "last_day", "team": "p_team"}),
                      left_on="gameday", right_on="last_day", by="player_id", allow_exact_matches=False)
    m = m[m.p_team == m.team]
    # only players who played in one of the team's last 3 games (older absences are already in teammates' numbers)
    m = m.merge(tg.rename(columns={"gameday": "last_day", "k": "k_last"}), on=["team", "last_day"], how="left")
    # index of this game in the team's schedule = number of team games before it (works for unplayed games too)
    before = {t: np.sort(x.gameday.values) for t, x in tg.groupby("team")}
    m["k_now"] = [np.searchsorted(before.get(t, np.array([], dtype=gd.dtype if hasattr(gd, "dtype") else "datetime64[ns]")), np.datetime64(gd), side="left")
                  for t, gd in zip(m.team, m.gameday)]
    m = m[(m.k_now - m.k_last) <= 3]
    m["grp"] = m.position.map(GROUP)
    agg = {"vac_t_all": ("post_targets", "sum"), "vac_c_all": ("post_carries", "sum")}
    r = m.groupby(["game_id", "team"]).agg(**agg)
    for grp in ("WR", "TE", "RB"):
        x = m[m.grp == grp].groupby(["game_id", "team"]).agg(t=("post_targets", "sum"), c=("post_carries", "sum"))
        r[f"vac_t_{grp}"], r[f"vac_c_{grp}"] = x.t, x.c
    return r.fillna(0).reset_index()


def _vac_pos(s: pd.DataFrame) -> pd.DataFrame:
    """vac_*_pos = what was freed up at the player's own position."""
    for c in ["vac_t_all", "vac_c_all"] + [f"vac_{k}_{g}" for k in "tc" for g in ("WR", "TE", "RB")]:
        if c not in s:
            s[c] = 0.0
        s[c] = s[c].fillna(0)
    pos = s["position"].map(GROUP).fillna("WR")
    s["vac_t_pos"] = np.select([pos == g for g in ("WR", "TE", "RB")], [s[f"vac_t_{g}"] for g in ("WR", "TE", "RB")], 0)
    s["vac_c_pos"] = np.select([pos == g for g in ("WR", "TE", "RB")], [s[f"vac_c_{g}"] for g in ("WR", "TE", "RB")], 0)
    return s


_FORM = {}


def with_opponent(rows: pd.DataFrame, s: pd.DataFrame, opp: str) -> pd.DataFrame:
    """Attach the upcoming opponent's defensive form (going into this game). Computed once per run."""
    if "f" not in _FORM:
        _FORM["f"], _FORM["p"] = defense_form(s, True), pressure_form(True)
    f = _FORM["f"]
    f = f[f["defense"] == opp].drop(columns="defense")
    r = rows.copy()
    for c in f:
        r[c] = f[c].iloc[0] if len(f) else np.nan
    dp, op = _FORM["p"]
    r["opp_pressure"] = dp.loc[dp["defense"] == opp, "opp_pressure"].squeeze() if (dp["defense"] == opp).any() else np.nan
    r = r.merge(op.rename(columns={"team": "team"}), on="team", how="left")
    return r


USE_NEW = True   # opponent defense + long-run (star) features, added Nov 15 - see v2/test_props.py --compare
USE_VAC = True      # Nov 23: targets/carries freed up by teammates listed Out/Doubtful (v2/test_props_new.py) - ON
VAC_SKIP = {"passing_yards"}   # it made passing yards slightly worse; used for every other market
USE_ROBUST = False  # Nov 23: share of last 8 games with a TD, and medians - one big game cannot skew them
ROBUST = ["receiving_yards", "rushing_yards", "passing_yards", "receptions", "targets", "carries"]
VAC = ["vac_t_all", "vac_c_all", "vac_t_pos", "vac_c_pos"]


def feats(market: str | None = None) -> list[str]:
    f = [f"ew_{c}" for c in RAW] + [f"last_{c}" for c in RAW] + ["ew_tds", "n_games", "pts", "spread_for", "home",
                                                                  "is_qb", "is_rb", "is_wr", "is_te"]
    if USE_NEW:
        f += [f"lr_{c}" for c in STAR] + [f"max_{c}" for c in STAR] + [f"opp_{c}" for c in DEF] + ["opp_pressure", "own_pressure_allowed"]
    if USE_ROBUST:
        f += [f"med8_{c}" for c in ROBUST] + ["td_rate8", "td_rate16"]
    if USE_VAC and market not in VAC_SKIP:
        f += VAC
    return f


def _pos(x):
    return x.assign(**{f"is_{p.lower()}": (x["position"] == p).astype(int) for p in ("QB", "RB", "WR", "TE")})


class StatModel:
    def __init__(self, market):
        self.market = market
        self.pos, self.f = STATS[market]

    def rows(self, s):
        x = s[s["position"].isin(self.pos) & (s["n_games"] >= 2)].copy()
        x["y"] = self.f(x)
        return _pos(x)

    def _m(self):
        return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=100, random_state=0)

    def fit(self, x):
        F = feats(self.market)
        pred = np.zeros(len(x))
        for sea in x["season"].unique():
            tr = x["season"] != sea
            pred[~tr] = self._m().fit(x.loc[tr, F], x.loc[tr, "y"]).predict(x.loc[~tr, F])
        self.m = self._m().fit(x[F], x["y"])
        if self.market == "anytime_td":
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.c = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300,
                                                    min_samples_leaf=100, random_state=0).fit(x[F], x["y"] >= 1)
        self.edges = np.unique(np.quantile(pred, np.linspace(0, 1, BINS + 1)))
        idx = np.clip(np.searchsorted(self.edges, pred, side="right") - 1, 0, len(self.edges) - 2)
        res = x["y"].values if (self.market in COUNTS and self.market not in RESID_COUNTS) else x["y"].values - pred
        self.vals = [np.sort(res[idx == i]) for i in range(len(self.edges) - 1)]
        if self.market in NEAR:
            o = np.argsort(pred)
            self.near_pred, self.near_y = pred[o], x["y"].values[o]
        return self

    def predict(self, x):
        if self.market == "anytime_td":   # a direct chance from a classifier (no cap at the top)
            return self.c.predict_proba(_pos(x)[feats(self.market)])[:, 1]
        return self.m.predict(_pos(x)[feats(self.market)])

    def p_reach(self, pred, rung):
        i = int(np.clip(np.searchsorted(self.edges, pred, side="right") - 1, 0, len(self.vals) - 1))
        v = self.vals[i]   # past misses (actual - predicted) of players with similar predictions
        if self.market == "anytime_td":
            return float(pred)
        if self.market in NEAR and hasattr(self, "near_pred"):   # the K closest projections, not a wide group
            k = NEAR[self.market]
            j = int(np.searchsorted(self.near_pred, pred))
            lo = max(0, min(j - k // 2, len(self.near_pred) - k))
            return float((self.near_y[lo:lo + k] >= rung).mean())
        if self.market in COUNTS and self.market not in RESID_COUNTS:   # whole numbers: actual outcomes of similar players
            return float((v >= rung).mean())
        return float((pred + v >= rung - 1e-9).mean())


def vacated_next(s: pd.DataFrame, out_ids: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """vac_* for upcoming games. out_ids: (team, player_id) Out/Doubtful/inactive now;
    games: (game_id, team, season, week, gameday)."""
    out = out_ids.merge(games[["team", "season", "week"]], on="team")
    return vacated(s, out=out, games=games)
