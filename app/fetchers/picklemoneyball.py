"""PickleMoneyBall — MLP-style events via the VSQ backend.

Two-tier: the public events list needs no login; your own per-event registration
(and partner) needs your credentials. A full roster of ALL registrants per division
is NOT exposed by this backend to normal users, so PMB feeds the Tournament Board
(events + your own sign-up status) but not the all-players cross-reference.

Auth (from the app bundle):
  POST {AUTH_API}/Login  header x-functions-key: <PMB_FUNC_KEY>  body {email,password}
       -> {success, accessToken:{token,expiresOn}, refreshToken:{...}}
  vsqApi calls use  Authorization: Bearer <token>  + AppVersion header.
PMB_FUNC_KEY comes from .env: it's the client key the PMB web app sends on Login —
grab it from the x-functions-key request header in your browser's network tab.
Without it the fetcher still pulls public events, just not your own sign-ups.
"""
from __future__ import annotations

from ..config import PMB_EMAIL, PMB_FUNC_KEY, PMB_PASSWORD
from ..geocode import geocode_city
from ..store import upsert_signup, upsert_tournament
from .base import FetchResult, Fetcher, make_client, polite_get, polite_post, register

AUTH_API = "https://vsq-functions-authentication.azurewebsites.net/api"
VSQ_API = "https://vsq-services-client.azurewebsites.net"
APP_VERSION = "1.6.1"


def _date(s: str | None) -> str | None:
    return s.split("T")[0] if s else None


def _login(client) -> str | None:
    if not PMB_FUNC_KEY:
        return None
    try:
        r = polite_post(client, f"{AUTH_API}/Login",
                        headers={"x-functions-key": PMB_FUNC_KEY},
                        json={"email": PMB_EMAIL, "password": PMB_PASSWORD})
        if r.status_code != 200:
            return None
        d = r.json()
        if not d.get("success", True):
            return None
        return (d.get("accessToken") or {}).get("token")
    except Exception:  # noqa: BLE001
        return None


def _divisions(e: dict) -> list[dict]:
    count = e.get("divisionCount")
    level = e.get("competitionLevel")
    label = "MLP / combined-rating"
    if count:
        label = f"{count} divisions · " + label
    if level:
        label += f" ({level})"
    return [{"name": label, "format": "mlp-3v15", "level": str(level or "")}]


def run() -> FetchResult:
    client = make_client(headers={"AppVersion": APP_VERSION, "Content-Type": "application/json"})
    token = None
    have_creds = bool(PMB_EMAIL and PMB_PASSWORD)
    if have_creds:
        token = _login(client)
        if token:
            client.headers["Authorization"] = f"Bearer {token}"

    try:
        r = polite_get(client, f"{VSQ_API}/event/GetPublicEvents")
        r.raise_for_status()
        events = r.json()
        if isinstance(events, dict):
            events = events.get("value") or events.get("events") or []
    except Exception as e:  # noqa: BLE001
        return FetchResult("picklemoneyball", "error", f"events fetch failed: {e}")

    n_t = n_s = 0
    for e in events:
        city, state = e.get("locationCity"), e.get("locationState")
        lat, lng = geocode_city(city, state)
        money = e.get("guaranteedMoney") or e.get("addedMoney")
        eid = e.get("id")
        tid = upsert_tournament({
            "name": e.get("name"),
            "source": "picklemoneyball",
            "source_key": str(eid),
            "source_url": e.get("websiteURL") or "https://picklemoneyball.com/",
            "registration_url": e.get("websiteURL") or "https://app.picklemoneyball.com/",
            "registration_platform": "picklemoneyball",
            "start_date": _date(e.get("startDate")),
            "end_date": _date(e.get("endDate")),
            "registration_deadline": _date(e.get("registrationEndDate")),
            "venue": e.get("locationName"),
            "city": city, "state": state,
            "lat": lat, "lng": lng,
            "divisions": _divisions(e),
            "entry_fee": f"${money:,} guaranteed" if isinstance(money, (int, float)) and money else None,
            "notes": (f"{e.get('playerCount')} players registered"
                      if e.get("playerCount") else None),
        })
        n_t += 1

        # With a token, record whether *you* are signed up (best available roster data).
        if token and eid is not None:
            try:
                ur = polite_get(client, f"{VSQ_API}/registration/GetUserByEvent",
                                params={"eventId": eid})
                if ur.status_code == 200:
                    reg = ur.json()
                    regs = reg.get("value") if isinstance(reg, dict) else reg
                    for entry in (regs or []) if isinstance(regs, list) else ([regs] if regs else []):
                        players = (entry or {}).get("players") or []
                        names = [
                            (p.get("player") or {}).get("displayName")
                            or " ".join(filter(None, [(p.get("player") or {}).get("firstName"),
                                                      (p.get("player") or {}).get("lastName")]))
                            for p in players
                        ]
                        names = [x for x in names if x]
                        for i, who in enumerate(names):
                            partner = names[1 - i] if len(names) == 2 else None
                            upsert_signup(tid, {
                                "player_name": who, "division": e.get("name"),
                                "partner_name": partner, "source": "picklemoneyball",
                            })
                            n_s += 1
            except Exception:  # noqa: BLE001
                pass

    tier = "auth" if token else ("no-token" if have_creds else "public-only")
    return FetchResult("picklemoneyball", "ok",
                       f"{n_t} events ({tier}), {n_s} own sign-ups",
                       tournaments=n_t, signups=n_s)


register(Fetcher("picklemoneyball", "PickleMoneyBall (events + your sign-ups)", "auth", run,
                 needs_credentials=["PMB_EMAIL", "PMB_PASSWORD"]))
