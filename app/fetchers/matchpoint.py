"""MatchPoint Open — public Shopify products.json feed (no login).

Each 'product' is an event: title carries name/venue/dates, body_html carries
divisions + the external registration URL (pickleballtournaments.com).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..dates import parse_date_range
from ..geocode import geocode_text
from ..store import upsert_tournament
from .base import FetchResult, Fetcher, make_client, polite_get, register

URL = "https://matchpointopen.com/collections/all-events/products.json"

_DATE_IN_PARENS = re.compile(r"\(([^)]*\d{4}[^)]*)\)")
_DIV_HINT = re.compile(r"(\d\.\d\+?|men'?s|women'?s|mixed|singles|doubles|open|challenger|senior)", re.I)


def _place_from_title(title: str) -> str:
    t = re.sub(r"^\s*tournament in\s*", "", title, flags=re.I)
    t = _DATE_IN_PARENS.sub("", t).strip(" -|")
    return t


def _divisions(body_html: str) -> list[dict]:
    text = BeautifulSoup(body_html or "", "html.parser").get_text(" ", strip=True)
    divs: list[dict] = []
    seen = set()
    for line in re.split(r"[\n\r]|(?<=[.;])\s", text):
        line = line.strip()
        if 3 < len(line) < 120 and _DIV_HINT.search(line):
            key = line.lower()
            if key not in seen:
                seen.add(key)
                divs.append({"name": line, "format": "", "level": ""})
        if len(divs) >= 12:
            break
    return divs or [{"name": "See event page", "format": "", "level": ""}]


def _registration_url(body_html: str) -> str | None:
    m = re.search(r"https?://[^\s\"'<>]*pickleballtournaments\.com[^\s\"'<>]*", body_html or "")
    return m.group(0) if m else None


def run() -> FetchResult:
    client = make_client()
    try:
        r = polite_get(client, URL)
        r.raise_for_status()
        products = r.json().get("products", [])
    except Exception as e:  # noqa: BLE001
        return FetchResult("matchpoint", "error", f"fetch failed: {e}")

    n = 0
    for p in products:
        title = p.get("title", "")
        if "coming soon" in title.lower():
            continue
        place = _place_from_title(title)
        dm = _DATE_IN_PARENS.search(title)
        start, end = parse_date_range(dm.group(1) if dm else None)
        lat, lng = geocode_text(place)
        body = p.get("body_html", "")
        upsert_tournament({
            "name": title,
            "source": "matchpoint",
            "source_key": p.get("handle") or str(p.get("id")),
            "source_url": f"https://matchpointopen.com/products/{p.get('handle')}",
            "registration_url": _registration_url(body),
            "registration_platform": "pickleballtournaments",
            "start_date": start, "end_date": end,
            "venue": place, "city": None, "state": None,
            "lat": lat, "lng": lng,
            "divisions": _divisions(body),
            "notes": (p.get("tags") or [""])[0] if p.get("tags") else None,
        })
        n += 1

    return FetchResult("matchpoint", "ok", f"{n} events", tournaments=n)


register(Fetcher("matchpoint", "MatchPoint Open (JSON)", "auto", run))
