"""SQLite storage: schema, connection helper, and upsert utilities."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    name_key          TEXT NOT NULL,              -- lowercased/normalized for dedupe
    dupr_id           TEXT,                        -- DUPR profile id if known
    dupr_doubles      REAL,
    dupr_singles      REAL,
    dupr_reliability  TEXT,                        -- verified / provisional / null
    city              TEXT,
    state             TEXT,
    club              TEXT,
    gender            TEXT,                        -- MALE / FEMALE / null
    age               INTEGER,
    lat               REAL,
    lng               REAL,
    instagram         TEXT,
    email             TEXT,
    phone             TEXT,
    image_url         TEXT,                        -- DUPR profile photo (for visual ID)
    youtube_search    TEXT,                        -- prebuilt search URL
    instagram_search  TEXT,                        -- prebuilt IG-scoped Google search URL
    google_search     TEXT,                        -- prebuilt general Google search URL
    contact_status    TEXT,                        -- found / partial / null (nothing yet)
    last_match_date   TEXT,                        -- most recent DUPR match (ISO date)
    last_match_checked TEXT,                        -- when we last looked it up
    source            TEXT,                        -- roster / dupr / manual
    manual_override   INTEGER DEFAULT 0,           -- 1 = user-edited, protect from refresh
    notes             TEXT,
    first_seen        TEXT DEFAULT (datetime('now')),
    last_updated      TEXT DEFAULT (datetime('now')),
    UNIQUE(name_key, dupr_id)
);
CREATE INDEX IF NOT EXISTS idx_players_doubles ON players(dupr_doubles);
CREATE INDEX IF NOT EXISTS idx_players_namekey ON players(name_key);

CREATE TABLE IF NOT EXISTS tournaments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    source            TEXT NOT NULL,               -- second_serve / az_cash / matchpoint / ...
    source_key        TEXT,                        -- stable id/slug within source
    source_url        TEXT,
    registration_url  TEXT,
    registration_platform TEXT,                    -- pickleballtournaments / pickleballden / ...
    start_date        TEXT,                        -- ISO yyyy-mm-dd
    end_date          TEXT,
    registration_deadline TEXT,
    venue             TEXT,
    city              TEXT,
    state             TEXT,
    lat               REAL,
    lng               REAL,
    nearest_metro     TEXT,
    metro_distance_mi REAL,
    divisions_json    TEXT,                        -- JSON list of {name, format, level}
    entry_fee         TEXT,
    combined_cap      REAL,                        -- combined-rating cap if known (Second Serve)
    rating_rules_json TEXT,                        -- per-event gender/age reduction rules (JSON)
    is_target         INTEGER DEFAULT 0,           -- matches your division filters
    manual_override   INTEGER DEFAULT 0,
    notes             TEXT,
    first_seen        TEXT DEFAULT (datetime('now')),
    last_updated      TEXT DEFAULT (datetime('now')),
    UNIQUE(source, source_key)
);
CREATE INDEX IF NOT EXISTS idx_tourn_start ON tournaments(start_date);

CREATE TABLE IF NOT EXISTS signups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    player_id     INTEGER REFERENCES players(id) ON DELETE SET NULL,
    player_name   TEXT NOT NULL,                   -- raw name as listed (may not resolve to a player row)
    division      TEXT,
    partner_name  TEXT,
    team_dupr     REAL,
    registered_at TEXT,
    source        TEXT,
    last_updated  TEXT DEFAULT (datetime('now')),
    UNIQUE(tournament_id, player_name, division)
);
CREATE INDEX IF NOT EXISTS idx_signups_tourn ON signups(tournament_id);
CREATE INDEX IF NOT EXISTS idx_signups_player ON signups(player_id);

CREATE TABLE IF NOT EXISTS fetch_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    status      TEXT NOT NULL,                     -- ok / error / skipped
    detail      TEXT,
    items_found INTEGER DEFAULT 0,
    ran_at      TEXT DEFAULT (datetime('now'))
);
"""


# Columns added after initial release — applied to pre-existing DBs on startup.
_MIGRATIONS = [
    ("players", "gender", "TEXT"),
    ("players", "age", "INTEGER"),
    ("players", "last_match_date", "TEXT"),
    ("players", "last_match_checked", "TEXT"),
    ("players", "image_url", "TEXT"),
    ("players", "instagram_search", "TEXT"),
    ("players", "google_search", "TEXT"),
    ("tournaments", "combined_cap", "REAL"),
    ("tournaments", "rating_rules_json", "TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, col, coltype in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
    # 'needs_lookup' placeholder retired in favor of stored search links
    conn.execute(
        "UPDATE players SET contact_status = NULL WHERE contact_status = 'needs_lookup'"
    )


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_fetch(source: str, status: str, detail: str = "", items_found: int = 0) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fetch_log (source, status, detail, items_found) VALUES (?,?,?,?)",
            (source, status, detail, items_found),
        )


def dict_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
