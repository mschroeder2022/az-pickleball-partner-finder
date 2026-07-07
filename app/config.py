"""Central configuration: your profile, target metros, division filters, credentials."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "azpb.db"

load_dotenv(BASE_DIR.parent / ".env")

# --- Your profile (set these in .env; generic Phoenix-area defaults) ----------
MY_NAME = os.getenv("MY_NAME", "Your Name")
MY_DUPR_DOUBLES = float(os.getenv("MY_DUPR_DOUBLES", "4.5") or "4.5")
MY_DUPR_SINGLES = float(os.getenv("MY_DUPR_SINGLES", "4.5") or "4.5")
HOME_BASE = os.getenv("HOME_BASE", "Phoenix, AZ")
HOME_LAT = float(os.getenv("HOME_LAT", "33.4484") or "33.4484")   # Phoenix center
HOME_LNG = float(os.getenv("HOME_LNG", "-112.0740") or "-112.0740")

# Partner rating window. The full +/-1.0 band is the *ceiling* filter; the
# tighter band is the realistic competitive sweet spot (highlighted in the UI).
RATING_CEILING_LOW = MY_DUPR_DOUBLES - 1.0
RATING_CEILING_HIGH = MY_DUPR_DOUBLES + 1.0
RATING_SWEET_LOW = float(os.getenv("RATING_SWEET_LOW", "") or round(MY_DUPR_DOUBLES - 0.5, 1))
RATING_SWEET_HIGH = float(os.getenv("RATING_SWEET_HIGH", "") or round(MY_DUPR_DOUBLES + 0.5, 1))

# What the DUPR fetch actually pulls. Defaults to the sweet spot (~937 players in
# 100mi of Phoenix, ~1.5 min). Widen toward the ceiling (3.92-5.92, ~3,400 players,
# ~5 min) if you want the full band in the local directory.
RATING_PULL_LOW = RATING_SWEET_LOW
RATING_PULL_HIGH = RATING_SWEET_HIGH

# Radius (miles) around Phoenix for the local AZ player search.
LOCAL_RADIUS_MILES = 100

# Activity: a player is "active" if they have a recorded DUPR match within this
# many days. The DUPR fetch looks up each player's last match (cached), and the
# Partner Finder filters to active players by default.
ACTIVITY_LOOKBACK_DAYS = 365
DUPR_HISTORY_DELAY = 0.4          # polite delay (s) for the per-player history lookups
DUPR_HISTORY_RECHECK_DAYS = 14    # skip re-checking a player looked up this recently
DUPR_MAX_HISTORY_CALLS = 2500     # safety cap on history lookups per refresh

# --- Target metros (100-mile radius) for national-circuit events --------------
# name -> (lat, lng). Phoenix/Tucson also anchor the local AZ search.
TARGET_METROS: dict[str, tuple[float, float]] = {
    "Detroit": (42.3314, -83.0458),
    "Chicago": (41.8781, -87.6298),
    "Phoenix": (33.4484, -112.0740),
    "Tucson": (32.2226, -110.9747),
    "San Diego": (32.7157, -117.1611),
    "Los Angeles": (34.0522, -118.2437),
    "Denver": (39.7392, -104.9903),
    "St. Louis": (38.6270, -90.1994),
    "Miami": (25.7617, -80.1918),
    "Tampa": (27.9506, -82.4572),
    "New Haven": (41.3083, -72.9279),
    "Boston": (42.3601, -71.0589),
    "Cleveland": (41.4993, -81.6944),
    "Fort Wayne": (41.0793, -85.1394),
    "Indianapolis": (39.7684, -86.1581),
    "Cedar Rapids": (41.9779, -91.6656),
    "Pacifica": (37.6138, -122.4869),
}
METRO_RADIUS_MILES = 100

# --- Combined-rating eligibility rules ---------------------------------------
# For combined-rating events (e.g. a "9.5" cap = your rating + partner's <= 9.5),
# some players get a rating "allowance": females and 50+ players count as lower.
# These are the DEFAULTS for AZ Cash / manual events. Second Serve events override
# them with the exact per-event values from that platform's API.
COMBINED_GENDER_TARGET = "FEMALE"     # which gender receives the allowance
COMBINED_GENDER_REDUCTION = 0.5       # rating knocked off a female partner
COMBINED_AGE_THRESHOLD = 50           # age at/above which the senior allowance applies
COMBINED_AGE_REDUCTION = 0.5          # rating knocked off a 50+ partner
COMBINED_STACK = True                 # a 50+ female gets BOTH allowances (0.5+0.5=1.0)
COMBINED_ROUND_ONE_DECIMAL = True     # round each player's DUPR to 1 decimal first
# Combined caps you care about (round-robin division levels), offered in the UI.
COMBINED_CAP_CHOICES = [8.5, 9.0, 9.5, 10.0]

# --- Division targeting -------------------------------------------------------
# Round-robin combined-rating events you care about, plus open + MLP formats.
TARGET_RR_LEVELS = {"8.5", "9", "9.0", "9.5", "10", "10.0"}
TARGET_MLP_LEVELS = {"18.5"}  # MLP-style combined-rating
# Substrings (lowercased) that mark a division as one you're targeting.
TARGET_DIVISION_KEYWORDS = [
    "open", "round robin", "round-robin", "3v15", "mlp", "18.5",
]

# --- Credentials (from .env) --------------------------------------------------
DUPR_EMAIL = os.getenv("DUPR_EMAIL", "").strip()
DUPR_PASSWORD = os.getenv("DUPR_PASSWORD", "").strip()
PMB_EMAIL = os.getenv("PMB_EMAIL", "").strip()
PMB_PASSWORD = os.getenv("PMB_PASSWORD", "").strip()
PMB_FUNC_KEY = os.getenv("PMB_FUNC_KEY", "").strip()
PBDEN_EMAIL = os.getenv("PBDEN_EMAIL", "").strip()
PBDEN_PASSWORD = os.getenv("PBDEN_PASSWORD", "").strip()

# --- Fetch politeness ---------------------------------------------------------
FETCH_MIN_DELAY_SECONDS = float(os.getenv("FETCH_MIN_DELAY_SECONDS", "2") or "2")
FETCH_USER_AGENT = os.getenv(
    "FETCH_USER_AGENT",
    "AZ-PB-Partner-Finder/1.0 (personal research tool)",
).strip()


def credentials_status() -> dict[str, bool]:
    """Which login-gated sources have credentials configured."""
    return {
        "dupr": bool(DUPR_EMAIL and DUPR_PASSWORD),
        "picklemoneyball": bool(PMB_EMAIL and PMB_PASSWORD),
        "app_tour": bool(PBDEN_EMAIL and PBDEN_PASSWORD),
    }
