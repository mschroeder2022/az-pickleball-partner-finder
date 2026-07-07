"""APP registrant lists via PickleballDen — DEFERRED.

PickleballDen is a Vaadin Flow app: session-cookie auth and a server-rendered
UIDL protocol, not a JSON REST API. Scraping registrant grids requires a headless
browser (Playwright) driving a real login, which is brittle and out of scope for
v1. The APP *schedule* (with registration deep links) is already captured by
app/fetchers/app_tour.py; use those links to review rosters manually.

Cleaner future path: request an API key for api.pickleballden.com (a real, key-
gated JSON API) and implement against it here.
"""
from __future__ import annotations

from ..config import PBDEN_EMAIL, PBDEN_PASSWORD
from .base import FetchResult, Fetcher, register


def run() -> FetchResult:
    if not (PBDEN_EMAIL and PBDEN_PASSWORD):
        return FetchResult("pickleballden", "skipped", "no PickleballDen credentials in .env")
    return FetchResult(
        "pickleballden", "skipped",
        "Deferred: PickleballDen is a Vaadin app needing a headless-browser login. "
        "Use the APP Tour registration links to review rosters manually, or request "
        "an api.pickleballden.com API key.",
    )


register(Fetcher("pickleballden", "APP registrants (deferred)", "auth", run,
                 needs_credentials=["PBDEN_EMAIL", "PBDEN_PASSWORD"]))
