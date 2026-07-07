"""Second Serve Sporting Goods — open JSON API (no login).

Provides tournaments AND public rosters (captain/partner names + combined DUPR),
which feed both the Tournament Board and the sign-up cross-reference.
"""
from __future__ import annotations

from ..geocode import geocode_text
from ..store import upsert_player, upsert_signup, upsert_tournament
from .base import FetchResult, Fetcher, make_client, polite_get, register

API = "https://app.secondservesportinggoods.com/api"


def _date(s: str | None) -> str | None:
    return s.split("T")[0] if s else None


def _divisions(t: dict) -> list[dict]:
    cap = t.get("combined_dupr_cap")
    name = t.get("name", "")
    level = str(cap) if cap is not None else ""
    return [{
        "name": name,
        "format": "round-robin" if (t.get("num_pools") or 0) else t.get("event_type", "doubles"),
        "level": level,
    }]


def run() -> FetchResult:
    client = make_client()
    try:
        r = polite_get(client, f"{API}/tournaments")
        r.raise_for_status()
        events = r.json()
    except Exception as e:  # noqa: BLE001
        return FetchResult("second_serve", "error", f"list fetch failed: {e}")

    n_t = n_p = n_s = 0
    for t in events:
        lat, lng = geocode_text(t.get("location_address") or t.get("location_name"))
        fee = t.get("entry_fee_cents")
        rating_rules = {
            "gender_target": (t.get("dupr_gender_target") or "female").upper(),
            "gender_reduction": t.get("dupr_gender_reduction") or 0.0,
            "reduce_by_gender": bool(t.get("dupr_reduce_by_gender")),
            "age_threshold": t.get("dupr_age_threshold"),
            "age_reduction": t.get("dupr_age_reduction"),
            "age_threshold_2": t.get("dupr_age_threshold_2"),
            "age_reduction_2": t.get("dupr_age_reduction_2"),
            "reduce_by_age": bool(t.get("dupr_reduce_by_age")),
            "stack": True,
            "round_one_decimal": bool(t.get("dupr_one_decimal_only")),
        }
        tid = upsert_tournament({
            "name": t.get("name"),
            "source": "second_serve",
            "source_key": t.get("slug") or str(t.get("id")),
            "source_url": f"https://secondservesportinggoods.com/tournaments/{t.get('slug')}",
            "registration_url": f"https://secondservesportinggoods.com/tournaments/{t.get('slug')}",
            "registration_platform": "second_serve",
            "start_date": _date(t.get("date_start")),
            "end_date": _date(t.get("date_end")),
            "registration_deadline": _date(t.get("registration_deadline")),
            "venue": t.get("location_name"),
            "city": None, "state": "AZ",
            "lat": lat, "lng": lng,
            "divisions": _divisions(t),
            "entry_fee": f"${fee/100:.0f}" if fee else None,
            "combined_cap": t.get("combined_dupr_cap"),
            "rating_rules": rating_rules,
        })
        n_t += 1

        # Rosters are public unless the organizer hides them.
        if t.get("privacy_mode") or t.get("hide_team_count"):
            continue
        slug = t.get("slug")
        if not slug:
            continue
        try:
            tr = polite_get(client, f"{API}/tournaments/{slug}/teams")
            if tr.status_code != 200:
                continue
            teams = tr.json()
        except Exception:  # noqa: BLE001
            continue
        for team in teams:
            team_dupr = team.get("combined_dupr")
            for who, partner in (
                (team.get("captain_name"), team.get("partner_name")),
                (team.get("partner_name"), team.get("captain_name")),
            ):
                if not who:
                    continue
                upsert_player({"name": who, "source": "roster", "state": "AZ"})
                n_p += 1
                upsert_signup(tid, {
                    "player_name": who,
                    "division": t.get("name"),
                    "partner_name": partner,
                    "team_dupr": team_dupr,
                    "registered_at": team.get("registered_at"),
                    "source": "second_serve",
                })
                n_s += 1

    return FetchResult("second_serve", "ok", f"{n_t} events, {n_s} signups",
                       tournaments=n_t, players=n_p, signups=n_s)


register(Fetcher("second_serve", "Second Serve (API)", "auto", run))
