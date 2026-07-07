"""DUPR — authenticated player search using the account owner's own credentials.

Verified live against DUPR's OpenAPI (SearchRequest / SearchFilter):
  POST /auth/v1.0/login/  {email,password}                 -> result.accessToken
  POST /player/v1.0/search {query:"*", limit<=25, offset,   -> result.hits[], result.total
        includeUnclaimedPlayers,
        filter:{ lat, lng, radiusInMeters,
                 rating:{minRating, maxRating, type:"DOUBLES"} }}

`query` must be non-empty ("*" = name-unfiltered). lat/lng/radiusInMeters are FLAT
inside `filter`; rating uses minRating/maxRating. By default we pull the realistic
partner band (RATING_PULL_LOW..HIGH, i.e. the 4.4-5.4 sweet spot) to keep the pull
fast and relevant; widen RATING_PULL_* in config.py for the full ceiling.

Note: DUPR's ToS restricts automated access; runs only with your own creds and
self-throttles.
"""
from __future__ import annotations

import time

from ..config import (
    DUPR_EMAIL,
    DUPR_HISTORY_DELAY,
    DUPR_HISTORY_RECHECK_DAYS,
    DUPR_MAX_HISTORY_CALLS,
    DUPR_PASSWORD,
    HOME_LAT,
    HOME_LNG,
    LOCAL_RADIUS_MILES,
    RATING_PULL_HIGH,
    RATING_PULL_LOW,
)
from ..store import players_needing_activity_check, set_player_activity, upsert_player
from .base import FetchResult, Fetcher, make_client, polite_get, polite_post, register

BASE = "https://api.dupr.gg"
MILES_TO_METERS = 1609.34
PAGE = 25
MAX_PAGES = 200  # safety cap (~5000 players)


def _login(client) -> str | None:
    r = polite_post(client, f"{BASE}/auth/v1.0/login/",
                    json={"email": DUPR_EMAIL, "password": DUPR_PASSWORD})
    if r.status_code != 200:
        return None
    return (r.json().get("result") or {}).get("accessToken")


def _search_page(client, offset: int):
    body = {
        "query": "*",
        "limit": PAGE,
        "offset": offset,
        "includeUnclaimedPlayers": True,
        "filter": {
            "lat": HOME_LAT,
            "lng": HOME_LNG,
            "radiusInMeters": int(LOCAL_RADIUS_MILES * MILES_TO_METERS),
            "rating": {
                "minRating": round(RATING_PULL_LOW, 2),
                "maxRating": round(RATING_PULL_HIGH, 2),
                "type": "DOUBLES",
            },
        },
    }
    return polite_post(client, f"{BASE}/player/v1.0/search", json=body)


def _rating(ratings: dict, key: str) -> float | None:
    try:
        return float(ratings.get(key))
    except (TypeError, ValueError):
        return None  # 'NR' / not rated


def run() -> FetchResult:
    if not (DUPR_EMAIL and DUPR_PASSWORD):
        return FetchResult("dupr", "skipped", "no DUPR credentials in .env")

    client = make_client(headers={"Content-Type": "application/json"})
    token = _login(client)
    if not token:
        return FetchResult("dupr", "error", "login failed (check DUPR credentials)")
    client.headers["Authorization"] = f"Bearer {token}"

    first = _search_page(client, 0)
    if first.status_code != 200:
        return FetchResult("dupr", "error",
                           f"search rejected (HTTP {first.status_code}): {first.text[:120]}")

    n = 0
    offset = 0
    total = None
    pages = 0
    while pages < MAX_PAGES:
        resp = first if offset == 0 else _search_page(client, offset)
        if resp.status_code == 429:
            time.sleep(5)
            continue
        if resp.status_code != 200:
            break
        result = resp.json().get("result") or {}
        hits = result.get("hits") or []
        total = result.get("total", total)
        for h in hits:
            ratings = h.get("ratings") or {}
            d = _rating(ratings, "doubles")
            s = _rating(ratings, "singles")
            name = h.get("fullName") or h.get("displayName") or ""
            if not name:
                continue
            loc = h.get("shortAddress") or h.get("formattedAddress") or ""
            city = loc.split(",")[0].strip() if loc else None
            gender = h.get("gender")
            age = h.get("age")
            upsert_player({
                "name": name,
                "dupr_id": str(h.get("id")) if h.get("id") is not None else None,
                "dupr_doubles": d, "dupr_singles": s,
                "dupr_reliability": "provisional" if ratings.get("doublesProvisional") else "verified",
                "city": city,
                "state": "AZ",
                "gender": gender.upper() if isinstance(gender, str) else None,
                "age": age if isinstance(age, int) else None,
                "image_url": h.get("imageUrl"),
                "source": "dupr",
            })
            n += 1
        pages += 1
        offset += PAGE
        if total is not None and offset >= total:
            break
        if not hits:
            break

    # --- Activity pass: look up each player's most recent DUPR match (cached) ---
    checked = _activity_pass(client)

    capped = " (page cap hit)" if pages >= MAX_PAGES else ""
    detail = f"{n} players in {RATING_PULL_LOW}-{RATING_PULL_HIGH} band{capped}"
    if checked:
        detail += f"; {checked} activity lookups"
    return FetchResult("dupr", "ok", detail, players=n)


def _latest_match_date(client, player_id: str) -> str | None:
    """Most recent match eventDate for a player, or None if no matches."""
    try:
        r = polite_get(
            client, f"{BASE}/player/v1.0/{player_id}/history?limit=3&offset=0",
            min_delay=DUPR_HISTORY_DELAY,
        )
        if r.status_code != 200:
            return None
        hits = (r.json().get("result") or {}).get("hits") or []
        dates = [h.get("eventDate") for h in hits if h.get("eventDate")]
        return max(dates) if dates else None
    except Exception:  # noqa: BLE001
        return None


def _activity_pass(client) -> int:
    """Populate last_match_date for DUPR players missing/stale, bounded by a cap."""
    todo = players_needing_activity_check(DUPR_HISTORY_RECHECK_DAYS)[:DUPR_MAX_HISTORY_CALLS]
    done = 0
    for p in todo:
        d = _latest_match_date(client, p["dupr_id"])
        set_player_activity(p["id"], d)
        done += 1
    return done


register(Fetcher("dupr", "DUPR player search", "auth", run,
                 needs_credentials=["DUPR_EMAIL", "DUPR_PASSWORD"]))
