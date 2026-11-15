"""Static team info: franchise continuity, stadium coordinates, time zones."""
import math

# Relocated franchises share ratings/form history with their current abbreviation.
FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA"}

# (lat, lon, UTC offset in standard time) of each team's home stadium.
STADIUM = {
    "ARI": (33.528, -112.263, -7), "ATL": (33.755, -84.401, -5), "BAL": (39.278, -76.623, -5),
    "BUF": (42.774, -78.787, -5), "CAR": (35.226, -80.853, -5), "CHI": (41.862, -87.617, -6),
    "CIN": (39.095, -84.516, -5), "CLE": (41.506, -81.700, -5), "DAL": (32.748, -97.093, -6),
    "DEN": (39.744, -105.020, -7), "DET": (42.340, -83.046, -5), "GB": (44.501, -88.062, -6),
    "HOU": (29.685, -95.411, -6), "IND": (39.760, -86.164, -5), "JAX": (30.324, -81.637, -5),
    "KC": (39.049, -94.484, -6), "LA": (33.953, -118.339, -8), "LAC": (33.953, -118.339, -8),
    "LV": (36.091, -115.184, -8), "MIA": (25.958, -80.239, -5), "MIN": (44.974, -93.258, -6),
    "NE": (42.091, -71.264, -5), "NO": (29.951, -90.081, -6), "NYG": (40.813, -74.074, -5),
    "NYJ": (40.813, -74.074, -5), "OAK": (37.751, -122.201, -8), "PHI": (39.901, -75.168, -5),
    "PIT": (40.447, -80.016, -5), "SD": (32.783, -117.120, -8), "SEA": (47.595, -122.332, -8),
    "SF": (37.403, -121.970, -8), "STL": (38.633, -90.188, -6), "TB": (27.976, -82.503, -5),
    "TEN": (36.166, -86.771, -6), "WAS": (38.908, -76.864, -5),
}

# Teams whose home field is a dome/closed roof (for "dome team playing in the cold").
DOME_TEAMS_BY_ERA = {
    "ARI": 2006, "ATL": 1992, "DAL": 2009, "DET": 1975, "HOU": 2002, "IND": 1984,
    "LA": 2020, "LAC": 2020, "LV": 2020, "MIN": 1982, "NO": 1975, "STL": 1995,
}


def franchise(team: str) -> str:
    return FRANCHISE.get(team, team)


def is_dome_team(team: str, season: int) -> bool:
    start = DOME_TEAMS_BY_ERA.get(team)
    if team == "MIN" and season in (2014, 2015):  # outdoors at TCF Bank Stadium
        return False
    if team in ("LA", "LAC") and season < 2020:
        return False
    return start is not None and season >= start


def miles(a: str, b: str) -> float:
    lat1, lon1, _ = STADIUM[a]
    lat2, lon2, _ = STADIUM[b]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 3959 * 2 * math.asin(math.sqrt(h))


def tz(team: str) -> int:
    return STADIUM[team][2]
