"""FastAPI app: serves the dashboard and the JSON API."""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .db import dict_rows, get_conn, init_db, log_fetch
from .eligibility import default_rules, evaluate
from .fetchers import all_fetchers, get_fetcher
from .geo import within_target_metro
from .store import (
    build_dupr_profile,
    build_google_search,
    build_instagram_search,
    build_youtube_search,
    relink_signups,
    upsert_player,
    upsert_tournament,
)


def _activity_cutoff() -> str:
    return (date.today() - timedelta(days=config.ACTIVITY_LOOKBACK_DAYS)).isoformat()


def enrich_player(p: dict, cutoff: str) -> dict:
    """Add research links and activity status to a player dict for the UI."""
    p["dupr_profile_url"] = build_dupr_profile(p.get("dupr_id"))
    if not p.get("google_search"):
        p["google_search"] = build_google_search(p["name"], p.get("city"))
    if not p.get("instagram_search"):
        p["instagram_search"] = build_instagram_search(p["name"])
    if not p.get("youtube_search"):
        p["youtube_search"] = build_youtube_search(p["name"])
    lmd = p.get("last_match_date")
    checked = bool(p.get("last_match_checked"))
    if lmd and lmd >= cutoff:
        p["activity_status"] = "active"
    elif checked:
        p["activity_status"] = "inactive"
    else:
        p["activity_status"] = "unknown"
    return p

app = FastAPI(title="AZ Pickleball Partner Finder")

# --- background refresh state ------------------------------------------------
_refresh_lock = threading.Lock()
_refresh_state: dict[str, Any] = {"running": False, "current": None, "results": []}


def _run_refresh(keys: list[str]) -> None:
    results = []
    for key in keys:
        f = get_fetcher(key)
        if not f:
            continue
        with _refresh_lock:
            _refresh_state["current"] = f.label
        try:
            res = f.run()
        except Exception as e:  # noqa: BLE001
            res = type("R", (), {"source": key, "status": "error",
                                 "detail": str(e), "tournaments": 0,
                                 "players": 0, "signups": 0})()
        log_fetch(res.source, res.status, res.detail,
                  getattr(res, "tournaments", 0) + getattr(res, "players", 0))
        results.append({
            "source": res.source, "status": res.status, "detail": res.detail,
            "tournaments": getattr(res, "tournaments", 0),
            "players": getattr(res, "players", 0),
            "signups": getattr(res, "signups", 0),
        })
        with _refresh_lock:
            _refresh_state["results"] = results
    relink_signups()
    with _refresh_lock:
        _refresh_state["running"] = False
        _refresh_state["current"] = None


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --- meta / status -----------------------------------------------------------
@app.get("/api/profile")
def profile() -> dict:
    return {
        "name": config.MY_NAME,
        "dupr_doubles": config.MY_DUPR_DOUBLES,
        "dupr_singles": config.MY_DUPR_SINGLES,
        "home_base": config.HOME_BASE,
        "rating_ceiling": [round(config.RATING_CEILING_LOW, 2), round(config.RATING_CEILING_HIGH, 2)],
        "rating_sweet": [config.RATING_SWEET_LOW, config.RATING_SWEET_HIGH],
        "metros": list(config.TARGET_METROS.keys()),
        "cap_choices": config.COMBINED_CAP_CHOICES,
    }


@app.get("/api/status")
def status() -> dict:
    with get_conn() as conn:
        counts = {
            "players": conn.execute("SELECT COUNT(*) c FROM players").fetchone()["c"],
            "tournaments": conn.execute("SELECT COUNT(*) c FROM tournaments").fetchone()["c"],
            "signups": conn.execute("SELECT COUNT(*) c FROM signups").fetchone()["c"],
        }
        log = dict_rows(conn.execute(
            "SELECT source, status, detail, ran_at FROM fetch_log ORDER BY id DESC LIMIT 20"
        ).fetchall())
    sources = [{
        "key": f.key, "label": f.label, "kind": f.kind,
        "needs_credentials": f.needs_credentials,
    } for f in all_fetchers()]
    return {
        "counts": counts,
        "credentials": config.credentials_status(),
        "sources": sources,
        "log": log,
        "refresh": _refresh_state,
    }


class RefreshReq(BaseModel):
    sources: list[str] | None = None  # None/empty => all


@app.post("/api/refresh")
def refresh(req: RefreshReq) -> dict:
    with _refresh_lock:
        if _refresh_state["running"]:
            raise HTTPException(409, "A refresh is already running")
        keys = req.sources or [f.key for f in all_fetchers()]
        _refresh_state.update(running=True, current=None, results=[])
    threading.Thread(target=_run_refresh, args=(keys,), daemon=True).start()
    return {"started": keys}


# --- players -----------------------------------------------------------------
@app.get("/api/players")
def players(
    min_rating: float | None = None,
    max_rating: float | None = None,
    sweet_only: bool = False,
    active_only: bool = True,
    search: str | None = None,
    sort: str = "dupr_doubles",
    order: str = "desc",
) -> list[dict]:
    lo = min_rating if min_rating is not None else config.RATING_CEILING_LOW
    hi = max_rating if max_rating is not None else config.RATING_CEILING_HIGH
    if sweet_only:
        lo, hi = config.RATING_SWEET_LOW, config.RATING_SWEET_HIGH
    sort_col = sort if sort in {
        "dupr_doubles", "dupr_singles", "name", "city", "contact_status",
        "last_match_date", "last_updated"
    } else "dupr_doubles"
    order_sql = "ASC" if order.lower() == "asc" else "DESC"

    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT * FROM players
                WHERE (dupr_doubles IS NULL OR dupr_doubles BETWEEN ? AND ?)
                  AND (? IS NULL OR name LIKE ?)
                ORDER BY {sort_col} IS NULL, {sort_col} {order_sql}""",
            (lo, hi, search, f"%{search}%" if search else None),
        ).fetchall()
        players_out = dict_rows(rows)
        # attach which upcoming tournaments each player is signed up for
        sup = conn.execute(
            """SELECT s.player_id, s.player_name, t.name AS tournament, t.start_date
               FROM signups s JOIN tournaments t ON t.id = s.tournament_id"""
        ).fetchall()
    by_pid: dict[int, list] = {}
    by_name: dict[str, list] = {}
    for s in sup:
        entry = {"tournament": s["tournament"], "start_date": s["start_date"]}
        if s["player_id"] is not None:
            by_pid.setdefault(s["player_id"], []).append(entry)
        by_name.setdefault((s["player_name"] or "").lower(), []).append(entry)
    cutoff = _activity_cutoff()
    out = []
    for p in players_out:
        signups = by_pid.get(p["id"]) or by_name.get((p["name"] or "").lower()) or []
        p["signups"] = signups
        p["in_sweet_spot"] = (
            p["dupr_doubles"] is not None
            and config.RATING_SWEET_LOW <= p["dupr_doubles"] <= config.RATING_SWEET_HIGH
        )
        enrich_player(p, cutoff)
        # Players with a signup are demonstrably active regardless of match lookup.
        if signups and p["activity_status"] == "unknown":
            p["activity_status"] = "active"
        if active_only and p["activity_status"] == "inactive":
            continue
        out.append(p)
    return out


class PlayerIn(BaseModel):
    name: str
    dupr_doubles: float | None = None
    dupr_singles: float | None = None
    city: str | None = None
    club: str | None = None
    instagram: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


@app.post("/api/players")
def add_player(p: PlayerIn) -> dict:
    data = p.model_dump()
    data["source"] = "manual"
    pid = upsert_player(data)
    with get_conn() as conn:
        conn.execute("UPDATE players SET manual_override = 1 WHERE id = ?", (pid,))
    return {"id": pid}


@app.put("/api/players/{pid}")
def edit_player(pid: int, p: PlayerIn) -> dict:
    fields = p.model_dump()
    sets = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        exists = conn.execute("SELECT id FROM players WHERE id = ?", (pid,)).fetchone()
        if not exists:
            raise HTTPException(404, "player not found")
        conn.execute(
            f"UPDATE players SET {sets}, manual_override = 1, last_updated = datetime('now') WHERE id = ?",
            (*fields.values(), pid),
        )
    return {"id": pid}


@app.delete("/api/players/{pid}")
def delete_player(pid: int) -> dict:
    with get_conn() as conn:
        conn.execute("DELETE FROM players WHERE id = ?", (pid,))
    return {"deleted": pid}


# --- tournaments -------------------------------------------------------------
@app.get("/api/tournaments")
def tournaments(
    target_only: bool = False,
    in_metro_only: bool = False,
    source: str | None = None,
    upcoming_only: bool = True,
) -> list[dict]:
    clauses, params = [], []
    if target_only:
        clauses.append("is_target = 1")
    if source:
        clauses.append("source = ?")
        params.append(source)
    if upcoming_only:
        clauses.append("(start_date IS NULL OR start_date >= date('now'))")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM tournaments {where} ORDER BY start_date IS NULL, start_date ASC",
            params,
        ).fetchall()
        out = dict_rows(rows)
        counts = {r["tournament_id"]: r["c"] for r in conn.execute(
            "SELECT tournament_id, COUNT(*) c FROM signups GROUP BY tournament_id"
        ).fetchall()}
    result = []
    for t in out:
        t["divisions"] = json.loads(t.get("divisions_json") or "[]")
        t["signup_count"] = counts.get(t["id"], 0)
        in_metro, metro, dist = within_target_metro(t.get("lat"), t.get("lng"))
        t["in_target_metro"] = in_metro
        if in_metro_only and not in_metro:
            continue
        result.append(t)
    return result


@app.get("/api/tournaments/{tid}/candidates")
def tournament_candidates(
    tid: int,
    cap: float | None = None,
    eligible_only: bool = False,
    active_only: bool = True,
) -> dict:
    """Players near you NOT signed up for this event, with combined-rating eligibility.

    `cap` overrides the combined-rating cap; if omitted, the tournament's own cap
    (Second Serve) is used. Each candidate is scored for pairing with you.
    """
    with get_conn() as conn:
        t = conn.execute("SELECT * FROM tournaments WHERE id = ?", (tid,)).fetchone()
        if not t:
            raise HTTPException(404, "tournament not found")
        signed = conn.execute(
            "SELECT player_id, player_name FROM signups WHERE tournament_id = ?", (tid,)
        ).fetchall()
        signed_ids = {s["player_id"] for s in signed if s["player_id"] is not None}
        signed_names = {(s["player_name"] or "").lower() for s in signed}
        rows = conn.execute(
            """SELECT * FROM players
               WHERE dupr_doubles BETWEEN ? AND ?
               ORDER BY dupr_doubles DESC""",
            (config.RATING_CEILING_LOW, config.RATING_CEILING_HIGH),
        ).fetchall()

    t = dict(t)
    effective_cap = cap if cap is not None else t.get("combined_cap")
    rules = (json.loads(t["rating_rules_json"]) if t.get("rating_rules_json")
             else default_rules())

    cutoff = _activity_cutoff()
    candidates = []
    for p in dict_rows(rows):
        if p["id"] in signed_ids or (p["name"] or "").lower() in signed_names:
            continue
        enrich_player(p, cutoff)
        if active_only and p["activity_status"] == "inactive":
            continue
        elig = evaluate(config.MY_DUPR_DOUBLES, p.get("dupr_doubles"), effective_cap,
                        p.get("gender"), p.get("age"), rules)
        p["eligibility"] = elig
        p["in_sweet_spot"] = (
            config.RATING_SWEET_LOW <= p["dupr_doubles"] <= config.RATING_SWEET_HIGH
        )
        if eligible_only and effective_cap is not None and not elig["eligible"]:
            continue
        candidates.append(p)

    # Eligible first, then closest-to-the-cap (strongest legal partner) first.
    def sort_key(p):
        e = p["eligibility"]
        elig_rank = 0 if e.get("eligible") else (1 if e.get("eligible") is False else 2)
        combined = e.get("combined")
        return (elig_rank, -(combined if combined is not None else -1))

    candidates.sort(key=sort_key)
    return {
        "tournament": t,
        "my_rating": config.MY_DUPR_DOUBLES,
        "cap": effective_cap,
        "cap_source": ("tournament" if cap is None and t.get("combined_cap") else
                       ("selected" if cap is not None else "none")),
        "rules": rules,
        "signed_up_count": len(signed),
        "eligible_count": sum(1 for c in candidates if c["eligibility"].get("eligible")),
        "candidates": candidates,
    }


class TournamentIn(BaseModel):
    name: str
    start_date: str | None = None
    end_date: str | None = None
    venue: str | None = None
    city: str | None = None
    state: str | None = None
    registration_url: str | None = None
    entry_fee: str | None = None
    notes: str | None = None


@app.post("/api/tournaments")
def add_tournament(t: TournamentIn) -> dict:
    data = t.model_dump()
    data.update(source="manual", source_key=t.name + "|" + (t.start_date or ""),
                divisions=[{"name": "manual entry", "format": "", "level": ""}])
    tid = upsert_tournament(data)
    with get_conn() as conn:
        conn.execute("UPDATE tournaments SET manual_override = 1 WHERE id = ?", (tid,))
    return {"id": tid}


@app.delete("/api/tournaments/{tid}")
def delete_tournament(tid: int) -> dict:
    with get_conn() as conn:
        conn.execute("DELETE FROM tournaments WHERE id = ?", (tid,))
    return {"deleted": tid}


# --- static frontend ---------------------------------------------------------
STATIC_DIR = config.BASE_DIR / "static"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


@app.get("/static/app.js")
def app_js() -> FileResponse:
    # Explicit UTF-8 charset so middots/arrows/emoji aren't mangled by the browser.
    return FileResponse(STATIC_DIR / "app.js",
                        media_type="application/javascript; charset=utf-8")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
