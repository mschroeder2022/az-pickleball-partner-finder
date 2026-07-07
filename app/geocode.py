"""Lightweight static geocoder: city/venue -> (lat, lng).

Avoids an external geocoding API (extra dependency + ToS). Covers Phoenix-metro
cities and the national target metros. Unknown places return (None, None), which
just means the tournament won't be distance-filtered (still shown in the board).
"""
from __future__ import annotations

import re

from .config import TARGET_METROS

# Phoenix-metro + common AZ cities.
_AZ_CITIES: dict[str, tuple[float, float]] = {
    "phoenix": (33.4484, -112.0740),
    "chandler": (33.3062, -111.8413),
    "tempe": (33.4255, -111.9400),
    "mesa": (33.4152, -111.8315),
    "gilbert": (33.3528, -111.7890),
    "scottsdale": (33.4942, -111.9261),
    "glendale": (33.5387, -112.1860),
    "peoria": (33.5806, -112.2374),
    "surprise": (33.6292, -112.3680),
    "goodyear": (33.4353, -112.3576),
    "avondale": (33.4356, -112.3496),
    "queen creek": (33.2487, -111.6343),
    "gold canyon": (33.3706, -111.4368),
    "fountain hills": (33.6117, -111.7174),
    "cave creek": (33.8334, -111.9509),
    "apache junction": (33.4151, -111.5496),
    "tucson": (32.2226, -110.9747),
    "flagstaff": (35.1983, -111.6513),
    "prescott": (34.5400, -112.4685),
}

# National city centroids (target metros + a few common event cities).
_US_CITIES: dict[str, tuple[float, float]] = {
    "detroit": (42.3314, -83.0458),
    "chicago": (41.8781, -87.6298),
    "san diego": (32.7157, -117.1611),
    "los angeles": (34.0522, -118.2437),
    "denver": (39.7392, -104.9903),
    "st. louis": (38.6270, -90.1994),
    "st louis": (38.6270, -90.1994),
    "saint louis": (38.6270, -90.1994),
    "miami": (25.7617, -80.1918),
    "tampa": (27.9506, -82.4572),
    "new haven": (41.3083, -72.9279),
    "boston": (42.3601, -71.0589),
    "cleveland": (41.4993, -81.6944),
    "fort wayne": (41.0793, -85.1394),
    "indianapolis": (39.7684, -86.1581),
    "cedar rapids": (41.9779, -91.6656),
    "pacifica": (37.6138, -122.4869),
    "macon": (32.8407, -83.6324),
    "daytona beach": (29.2108, -81.0228),
    "holly hill": (29.2436, -81.0470),
    "naples": (26.1420, -81.7948),
    "overland park": (38.9822, -94.6708),
    "columbus": (39.9612, -82.9988),
    "kansas city": (39.0997, -94.5786),
    "dallas": (32.7767, -96.7970),
    "allen": (33.1032, -96.6706),
    "san antonio": (29.4241, -98.4936),
    "webster": (29.5377, -95.1183),
    "grapevine": (32.9343, -97.0781),
    "cincinnati": (39.1031, -84.5120),
    "hamilton": (39.3995, -84.5613),
    "corona": (33.8753, -117.5664),
    "sheridan": (39.6547, -105.0231),
    "seattle": (47.6062, -122.3321),
    "grand rapids": (42.9634, -85.6681),
    "charlotte": (35.2271, -80.8431),
    "eau claire": (44.8113, -91.4985),
    "peachtree city": (33.3968, -84.5963),
    "englewood": (26.9620, -82.3529),
    "sarasota": (27.3364, -82.5307),
    "spring valley": (32.7448, -116.9989),   # near San Diego
    "fort lauderdale": (26.1224, -80.1373),  # near Miami
    "orange park": (30.1663, -81.7062),
    "las vegas": (36.1699, -115.1398),
    "jacksonville": (30.3322, -81.6557),
}

# Well-known venue names -> (lat, lng), used as a fallback for venue-only strings.
_VENUES: dict[str, tuple[float, float]] = {
    "arizona athletic grounds": (33.4152, -111.8315),   # Mesa AZ
    "az athletic grounds": (33.4152, -111.8315),
    "pictona": (29.2436, -81.0470),                     # Holly Hill FL
    "eagle glen": (33.8753, -117.5664),                 # Corona CA
    "3rd shot river point": (39.6547, -105.0231),       # Sheridan/Denver CO
    "chicken n pickle overland park": (38.9822, -94.6708),
    "vibe credit union showplace": (42.3314, -83.0458),
    "danny cunniff park": (41.8781, -87.6298),
}

_ALL = {**{k.lower(): v for k, v in _AZ_CITIES.items()},
        **{k.lower(): v for k, v in _US_CITIES.items()},
        **{k.lower(): v for k, v in _VENUES.items()},
        **{k.lower(): v for k, v in TARGET_METROS.items()}}


def geocode_city(city: str | None, state: str | None = None) -> tuple[float | None, float | None]:
    if not city:
        return None, None
    key = city.strip().lower()
    if key in _ALL:
        return _ALL[key]
    # try stripping directionals / extra tokens
    key2 = re.sub(r"\b(north|south|east|west|greater)\b", "", key).strip()
    if key2 in _ALL:
        return _ALL[key2]
    return None, None


def geocode_text(text: str | None) -> tuple[float | None, float | None]:
    """Best-effort: scan a free-text venue/address string for a known city name."""
    if not text:
        return None, None
    low = text.lower()
    # longest names first so 'los angeles' wins before 'angeles', etc.
    for name in sorted(_ALL, key=len, reverse=True):
        if name in low:
            return _ALL[name]
    return None, None
