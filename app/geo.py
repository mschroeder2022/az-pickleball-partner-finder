"""Geographic helpers: haversine distance and nearest-target-metro matching."""
from __future__ import annotations

import math

from .config import METRO_RADIUS_MILES, TARGET_METROS

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def nearest_metro(lat: float | None, lng: float | None) -> tuple[str | None, float | None]:
    """Return (metro_name, miles) for the closest target metro, or (None, None)."""
    if lat is None or lng is None:
        return None, None
    best_name, best_dist = None, None
    for name, (mlat, mlng) in TARGET_METROS.items():
        d = haversine_miles(lat, lng, mlat, mlng)
        if best_dist is None or d < best_dist:
            best_name, best_dist = name, d
    return best_name, best_dist


def within_target_metro(lat: float | None, lng: float | None) -> tuple[bool, str | None, float | None]:
    """True if the point is within METRO_RADIUS_MILES of any target metro."""
    name, dist = nearest_metro(lat, lng)
    if dist is None:
        return False, None, None
    return dist <= METRO_RADIUS_MILES, name, dist
