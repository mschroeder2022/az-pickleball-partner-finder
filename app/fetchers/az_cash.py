"""AZ Cash Tournaments — parse schema.org JSON-LD from the server-rendered homepage.

Aggregator/calendar: gives events + registration links (no rosters). Registration
happens on downstream platforms (Vizual Spots / Paddle Battles / Second Serve / IG).
"""
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from ..geocode import geocode_city, geocode_text
from ..store import upsert_tournament
from .base import FetchResult, Fetcher, make_client, polite_get, register

URL = "https://www.azcashtournaments.com/"


def _platform(url: str | None) -> str | None:
    if not url:
        return None
    for host, name in (
        ("vizualspots", "vizual_spots"),
        ("paddlebattles", "paddle_battles"),
        ("secondserve", "second_serve"),
        ("instagram", "instagram"),
        ("pickleballbrackets", "pickleballbrackets"),
        ("pickleballtournaments", "pickleballtournaments"),
    ):
        if host in url:
            return name
    return None


def _iter_events(node):
    """Yield SportsEvent dicts from a possibly-nested JSON-LD structure."""
    if isinstance(node, dict):
        if node.get("@type") == "SportsEvent":
            yield node
        for key in ("@graph", "itemListElement"):
            for child in node.get(key, []) or []:
                yield from _iter_events(child)
        if "item" in node:
            yield from _iter_events(node["item"])
    elif isinstance(node, list):
        for child in node:
            yield from _iter_events(child)


def run() -> FetchResult:
    client = make_client()
    try:
        r = polite_get(client, URL)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return FetchResult("az_cash", "error", f"fetch failed: {e}")

    soup = BeautifulSoup(r.text, "html.parser")
    events: list[dict] = []
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(block.string or "")
        except Exception:  # noqa: BLE001
            continue
        events.extend(_iter_events(data))

    n = 0
    for e in events:
        loc = e.get("location") or {}
        addr = loc.get("address") or {}
        city = addr.get("addressLocality")
        state = addr.get("addressRegion")
        lat, lng = geocode_city(city, state)
        if lat is None:
            lat, lng = geocode_text(loc.get("name") or e.get("name"))
        offer = e.get("offers") or {}
        reg_url = offer.get("url") or e.get("url")
        price = offer.get("price")
        upsert_tournament({
            "name": e.get("name"),
            "source": "az_cash",
            "source_key": (e.get("name", "") + "|" + (e.get("startDate") or "")).strip("|"),
            "source_url": e.get("url"),
            "registration_url": reg_url,
            "registration_platform": _platform(reg_url),
            "start_date": (e.get("startDate") or "").split("T")[0] or None,
            "end_date": (e.get("endDate") or "").split("T")[0] or None,
            "venue": loc.get("name"),
            "city": city, "state": state,
            "lat": lat, "lng": lng,
            "divisions": [{"name": e.get("name", ""), "format": "", "level": ""}],
            "entry_fee": f"${price}" if price else None,
            "notes": e.get("description"),
        })
        n += 1

    return FetchResult("az_cash", "ok", f"{n} events", tournaments=n)


register(Fetcher("az_cash", "AZ Cash Tournaments (JSON-LD)", "auto", run))
