"""PPA Challenger — server-rendered WordPress schedule (polite auto-fetch).

robots.txt permits /schedule/ with a 3s crawl-delay; the app's global throttle
covers that. Registration funnels to pickleballtournaments.com.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..dates import parse_date_range
from ..geocode import geocode_city
from ..store import upsert_tournament
from .base import FetchResult, Fetcher, make_client, polite_get, register

URL = "https://ppachallenger.com/schedule/"

# 'July 17-19, 2026  City, ST' or 'July 31-August 2, 2026  City, ST'
_EVENT_RE = re.compile(
    r"([A-Z][a-z]+ \d{1,2}\s*-\s*(?:[A-Z][a-z]+ )?\d{1,2},\s*\d{4})\s+([A-Za-z .]+?),\s*([A-Z]{2})\b"
)


def run() -> FetchResult:
    client = make_client()
    try:
        r = polite_get(client, URL)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return FetchResult("ppa_challenger", "error", f"fetch failed: {e}")

    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    # Detail links in document order (deduped) to attach as source_url.
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/tournament/" in href and href not in links:
            links.append(href)

    events = list(_EVENT_RE.finditer(text))
    n = 0
    for i, m in enumerate(events):
        date_str, city, state = m.group(1), m.group(2).strip(), m.group(3)
        start, end = parse_date_range(date_str)
        lat, lng = geocode_city(city, state)
        detail = links[i] if i < len(links) else None
        upsert_tournament({
            "name": f"{city} PPA Challenger",
            "source": "ppa_challenger",
            "source_key": f"{city}-{state}-{start or date_str}",
            "source_url": detail or URL,
            "registration_url": detail or URL,
            "registration_platform": "pickleballtournaments",
            "start_date": start, "end_date": end,
            "city": city, "state": state,
            "lat": lat, "lng": lng,
            "divisions": [
                {"name": "Amateur brackets 1.0-5.0 (singles/doubles/mixed)",
                 "format": "open", "level": ""},
            ],
        })
        n += 1

    return FetchResult("ppa_challenger", "ok", f"{n} events", tournaments=n)


register(Fetcher("ppa_challenger", "PPA Challenger (HTML)", "auto", run))
