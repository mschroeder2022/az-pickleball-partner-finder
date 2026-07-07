"""Shared HTTP client with per-host politeness throttling and a fetcher registry."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import httpx

from ..config import FETCH_MIN_DELAY_SECONDS, FETCH_USER_AGENT

_last_hit: dict[str, float] = {}
_lock = threading.Lock()


def _throttle(url: str, min_delay: float | None = None) -> None:
    host = urlparse(url).netloc
    delay = FETCH_MIN_DELAY_SECONDS if min_delay is None else min_delay
    with _lock:
        now = time.monotonic()
        prev = _last_hit.get(host, 0.0)
        wait = delay - (now - prev)
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.monotonic()


def make_client(headers: dict[str, str] | None = None, timeout: float = 30.0) -> httpx.Client:
    base_headers = {"User-Agent": FETCH_USER_AGENT, "Accept": "application/json, text/html;q=0.9"}
    if headers:
        base_headers.update(headers)
    return httpx.Client(headers=base_headers, timeout=timeout, follow_redirects=True)


def polite_get(client: httpx.Client, url: str, min_delay: float | None = None, **kwargs) -> httpx.Response:
    _throttle(url, min_delay)
    return client.get(url, **kwargs)


def polite_post(client: httpx.Client, url: str, min_delay: float | None = None, **kwargs) -> httpx.Response:
    _throttle(url, min_delay)
    return client.post(url, **kwargs)


@dataclass
class FetchResult:
    source: str
    status: str  # ok / error / skipped
    detail: str = ""
    tournaments: int = 0
    players: int = 0
    signups: int = 0


# --- Fetcher registry --------------------------------------------------------
@dataclass
class Fetcher:
    key: str
    label: str
    kind: str  # "auto" (no login) or "auth" (needs credentials)
    run: Callable[[], FetchResult]
    needs_credentials: list[str] = field(default_factory=list)


_REGISTRY: dict[str, Fetcher] = {}


def register(fetcher: Fetcher) -> None:
    _REGISTRY[fetcher.key] = fetcher


def all_fetchers() -> list[Fetcher]:
    return list(_REGISTRY.values())


def get_fetcher(key: str) -> Fetcher | None:
    return _REGISTRY.get(key)
