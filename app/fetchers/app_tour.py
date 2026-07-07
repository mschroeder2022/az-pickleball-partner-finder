"""APP Tour — server-rendered Webflow schedule (no login).

Extracts events + their PickleballDen registration IDs. Registrant lists live in
PickleballDen (Vaadin app, session-cookie auth) and are NOT auto-fetchable here;
this fetcher delivers the schedule + a deep registration link for manual roster
review. See app/fetchers/pickleballden.py for the (deferred) roster path.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..geocode import geocode_text
from ..store import upsert_tournament
from .base import FetchResult, Fetcher, make_client, polite_get, register

URL = "https://www.theapp.global/tour"

# 'DD Mon - DD Mon YYYY'  e.g. '31 Jul - 02 Aug 2026'
_DATE_RE = re.compile(
    r"(\d{1,2})\s+([A-Za-z]{3})\s*-\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})"
)
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
           "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def _dates(text: str) -> tuple[str | None, str | None]:
    m = _DATE_RE.search(text)
    if not m:
        return None, None
    d1, mon1, d2, mon2, yr = m.groups()
    y = int(yr)
    m1, m2 = _MONTHS.get(mon1.lower()[:3]), _MONTHS.get(mon2.lower()[:3])
    if not (m1 and m2):
        return None, None
    return f"{y:04d}-{m1:02d}-{int(d1):02d}", f"{y:04d}-{m2:02d}-{int(d2):02d}"


def _card_text(link_tag):
    """Climb to the card container that includes the event's date text."""
    node = link_tag
    for _ in range(6):
        if not node.parent:
            break
        node = node.parent
        txt = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if _DATE_RE.search(txt) and "20" in txt:
            return txt
    return re.sub(r"\s+", " ", link_tag.parent.get_text(" ", strip=True)) if link_tag.parent else ""


_STOP = ("Register", "Buy Tickets", "Buy Ticket", "Learn More", "More Info",
         "Text Link", "Details", "Sign Up")


def _split_venue_title(text: str) -> tuple[str, str]:
    """Text is '<venue> <YYYY... APP ...> <Register/date junk>'.

    Title starts at the first year (keeping a leading 'The' if present) and ends
    at the first call-to-action word or date fragment.
    """
    m = re.search(r"(?:The\s+)?(20\d{2})", text)
    if not m:
        return "", text[:80].strip()
    start = m.start()
    title = text[start:]
    for junk in _STOP:
        i = title.find(junk)
        if i != -1:
            title = title[:i]
    # drop trailing date fragments like '31 - 02' / '31 Jul'
    title = re.split(r"\s+\d{1,2}\s*[-–]\s*\d{1,2}\b", title)[0]
    title = re.sub(r"\s+", " ", title).strip(" -·")
    venue = re.sub(r"\s+", " ", text[:start]).strip(" -·")
    return venue, title


def run() -> FetchResult:
    client = make_client()
    try:
        r = polite_get(client, URL)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return FetchResult("app_tour", "error", f"fetch failed: {e}")

    soup = BeautifulSoup(r.text, "html.parser")
    n = 0
    seen_ids: set[str] = set()
    for a in soup.find_all("a", href=re.compile(r"external-tournament/\d+")):
        m = re.search(r"external-tournament/(\d+)", a["href"])
        if not m:
            continue
        pbid = m.group(1)
        if pbid in seen_ids:
            continue
        seen_ids.add(pbid)
        text = _card_text(a)
        venue, title = _split_venue_title(text)
        if not title:
            continue
        start, end = _dates(text)
        lat, lng = geocode_text(venue + " " + title)
        is_qualifier = "qualifier" in title.lower()
        upsert_tournament({
            "name": title,
            "source": "app_tour",
            "source_key": pbid,
            "source_url": URL,
            "registration_url": a["href"],
            "registration_platform": "pickleballden",
            "start_date": start, "end_date": end,
            "venue": venue or None,
            "lat": lat, "lng": lng,
            "divisions": [
                {"name": "APP amateur age/skill divisions"
                          + (" + Qualifier" if is_qualifier else ""),
                 "format": "open", "level": ""},
            ],
            "notes": "Qualifier event" if is_qualifier else None,
        })
        n += 1

    return FetchResult("app_tour", "ok", f"{n} events", tournaments=n)


register(Fetcher("app_tour", "APP Tour (HTML schedule)", "auto", run))
