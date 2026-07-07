"""Upsert helpers that dedupe players/tournaments and respect manual overrides."""
from __future__ import annotations

import json
import re
from typing import Any

from .config import (
    RATING_CEILING_HIGH,
    RATING_CEILING_LOW,
    TARGET_DIVISION_KEYWORDS,
)
from .db import dict_rows, get_conn
from .geo import nearest_metro

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]")


def name_key(name: str) -> str:
    """Normalize a display name for dedupe: lowercase, strip punctuation/extra spaces."""
    s = (name or "").strip().lower()
    s = _NON_ALNUM.sub("", s)
    return _WS.sub(" ", s).strip()


def build_youtube_search(name: str) -> str:
    from urllib.parse import quote_plus

    return "https://www.youtube.com/results?search_query=" + quote_plus(
        f"{name} arizona pickleball"
    )


def build_instagram_search(name: str) -> str:
    """A Google search biased toward the player's Instagram profile."""
    from urllib.parse import quote_plus

    return "https://www.google.com/search?q=" + quote_plus(
        f'{name} arizona pickleball site:instagram.com'
    )


def build_google_search(name: str, city: str | None = None) -> str:
    """General Google search: quoted name + pickleball + their city (best first stop)."""
    from urllib.parse import quote_plus

    where = f"{city} AZ" if city else "Arizona"
    return "https://www.google.com/search?q=" + quote_plus(
        f'"{name}" pickleball {where}'
    )


def build_dupr_profile(dupr_id: str | None) -> str | None:
    if not dupr_id:
        return None
    return f"https://dashboard.dupr.com/dashboard/player/{dupr_id}"


def contact_status_for(instagram: str | None, email: str | None, phone: str | None) -> str | None:
    if email or phone:
        return "found"
    if instagram:
        return "partial"
    return None  # nothing yet — the stored search links are the starting point


def upsert_player(p: dict[str, Any]) -> int:
    """Insert or update a player, matching on normalized name (+ dupr_id when present).

    Never overwrites a row whose manual_override=1 except to fill NULL fields.
    Returns the player id.
    """
    nk = name_key(p["name"])
    dupr_id = p.get("dupr_id")
    yt = p.get("youtube_search") or build_youtube_search(p["name"])
    ig = p.get("instagram_search") or build_instagram_search(p["name"])
    gg = p.get("google_search") or build_google_search(p["name"], p.get("city"))
    cstatus = p.get("contact_status") or contact_status_for(
        p.get("instagram"), p.get("email"), p.get("phone")
    )
    with get_conn() as conn:
        # Match on dupr_id if we have one, else on name_key.
        row = None
        if dupr_id:
            row = conn.execute(
                "SELECT * FROM players WHERE dupr_id = ?", (dupr_id,)
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM players WHERE name_key = ? ORDER BY id LIMIT 1", (nk,)
            ).fetchone()

        fields = dict(
            name=p["name"], name_key=nk, dupr_id=dupr_id,
            dupr_doubles=p.get("dupr_doubles"), dupr_singles=p.get("dupr_singles"),
            dupr_reliability=p.get("dupr_reliability"),
            city=p.get("city"), state=p.get("state"), club=p.get("club"),
            gender=p.get("gender"), age=p.get("age"),
            lat=p.get("lat"), lng=p.get("lng"),
            instagram=p.get("instagram"), email=p.get("email"), phone=p.get("phone"),
            image_url=p.get("image_url"),
            youtube_search=yt, instagram_search=ig, google_search=gg,
            contact_status=cstatus, source=p.get("source"),
            last_match_date=p.get("last_match_date"),
            last_match_checked=p.get("last_match_checked"),
            notes=p.get("notes"),
        )
        if row is None:
            cols = ", ".join(fields)
            ph = ", ".join(["?"] * len(fields))
            cur = conn.execute(
                f"INSERT INTO players ({cols}) VALUES ({ph})", tuple(fields.values())
            )
            return cur.lastrowid

        pid = row["id"]
        protected = row["manual_override"] == 1
        sets, vals = [], []
        for col, val in fields.items():
            if col in ("name_key",):
                continue
            if protected:
                # only fill columns that are currently NULL/empty
                if row[col] not in (None, ""):
                    continue
            if val is None:
                continue
            sets.append(f"{col} = ?")
            vals.append(val)
        if sets:
            sets.append("last_updated = datetime('now')")
            vals.append(pid)
            conn.execute(f"UPDATE players SET {', '.join(sets)} WHERE id = ?", vals)
        return pid


def players_needing_activity_check(recheck_days: int) -> list[dict[str, Any]]:
    """DUPR players whose last-match lookup is missing or older than recheck_days."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, dupr_id FROM players
               WHERE source = 'dupr' AND dupr_id IS NOT NULL
                 AND (last_match_checked IS NULL
                      OR last_match_checked < datetime('now', ?))
               ORDER BY id""",
            (f"-{int(recheck_days)} days",),
        ).fetchall()
    return dict_rows(rows)


def set_player_activity(player_id: int, last_match_date: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE players SET last_match_date = ?, last_match_checked = datetime('now') WHERE id = ?",
            (last_match_date, player_id),
        )


def division_is_target(divisions: list[dict[str, Any]]) -> bool:
    for d in divisions or []:
        text = " ".join(
            str(d.get(k, "")) for k in ("name", "format", "level")
        ).lower()
        if any(kw in text for kw in TARGET_DIVISION_KEYWORDS):
            return True
        # combined-rating round-robin levels like 8.5/9/9.5/10
        for lvl in ("8.5", "9.5", "10", "9", "18.5"):
            if lvl in text and ("rr" in text or "round" in text or "combined" in text or "mlp" in text):
                return True
    return False


def upsert_tournament(t: dict[str, Any]) -> int:
    """Insert or update a tournament, keyed on (source, source_key)."""
    divisions = t.get("divisions") or []
    lat, lng = t.get("lat"), t.get("lng")
    metro, dist = nearest_metro(lat, lng)
    is_target = 1 if division_is_target(divisions) else 0
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tournaments WHERE source = ? AND source_key = ?",
            (t["source"], t.get("source_key")),
        ).fetchone()
        fields = dict(
            name=t["name"], source=t["source"], source_key=t.get("source_key"),
            source_url=t.get("source_url"), registration_url=t.get("registration_url"),
            registration_platform=t.get("registration_platform"),
            start_date=t.get("start_date"), end_date=t.get("end_date"),
            registration_deadline=t.get("registration_deadline"),
            venue=t.get("venue"), city=t.get("city"), state=t.get("state"),
            lat=lat, lng=lng, nearest_metro=metro, metro_distance_mi=dist,
            divisions_json=json.dumps(divisions), entry_fee=t.get("entry_fee"),
            combined_cap=t.get("combined_cap"),
            rating_rules_json=json.dumps(t["rating_rules"]) if t.get("rating_rules") else None,
            is_target=is_target, notes=t.get("notes"),
        )
        if row is None:
            cols = ", ".join(fields)
            ph = ", ".join(["?"] * len(fields))
            cur = conn.execute(
                f"INSERT INTO tournaments ({cols}) VALUES ({ph})", tuple(fields.values())
            )
            return cur.lastrowid
        tid = row["id"]
        if row["manual_override"] == 1:
            return tid  # leave user-owned rows alone entirely
        sets = [f"{c} = ?" for c in fields if c not in ("source", "source_key")]
        vals = [fields[c] for c in fields if c not in ("source", "source_key")]
        sets.append("last_updated = datetime('now')")
        vals.append(tid)
        conn.execute(f"UPDATE tournaments SET {', '.join(sets)} WHERE id = ?", vals)
        return tid


def upsert_signup(tournament_id: int, s: dict[str, Any]) -> None:
    """Record a player's registration in a tournament; link to a player row if resolvable."""
    pname = s["player_name"]
    nk = name_key(pname)
    with get_conn() as conn:
        prow = conn.execute(
            "SELECT id FROM players WHERE name_key = ? ORDER BY id LIMIT 1", (nk,)
        ).fetchone()
        player_id = prow["id"] if prow else None
        conn.execute(
            """INSERT INTO signups
               (tournament_id, player_id, player_name, division, partner_name,
                team_dupr, registered_at, source)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(tournament_id, player_name, division) DO UPDATE SET
                 player_id=excluded.player_id, partner_name=excluded.partner_name,
                 team_dupr=excluded.team_dupr, registered_at=excluded.registered_at,
                 last_updated=datetime('now')""",
            (tournament_id, player_id, pname, s.get("division"), s.get("partner_name"),
             s.get("team_dupr"), s.get("registered_at"), s.get("source")),
        )


def relink_signups() -> None:
    """After a player refresh, connect unresolved signup rows to known player rows."""
    with get_conn() as conn:
        players = conn.execute("SELECT id, name_key FROM players").fetchall()
        by_key = {p["name_key"]: p["id"] for p in players}
        unlinked = conn.execute(
            "SELECT id, player_name FROM signups WHERE player_id IS NULL"
        ).fetchall()
        for s in unlinked:
            pid = by_key.get(name_key(s["player_name"]))
            if pid:
                conn.execute(
                    "UPDATE signups SET player_id = ? WHERE id = ?", (pid, s["id"])
                )
