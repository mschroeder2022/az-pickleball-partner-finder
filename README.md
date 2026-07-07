# AZ Pickleball Partner Finder

A local, single-user research dashboard for finding doubles partners for upcoming
tournaments in Arizona and target metros. It aggregates tournaments, harvests public
sign-up rosters (with DUPR ratings where available), and cross-references who near
you at your level is **not yet signed up** — so you can reach out manually.

Set your own profile in `.env` (name, DUPR ratings, home base coordinates) — the
partner sweet spot (±0.5) and filter ceiling (±1.0) derive from your rating.

## Quick start

```bash
py -m pip install -r requirements.txt      # first time only
cp .env.example .env                        # then edit .env (see below)
py run.py                                    # opens http://127.0.0.1:8000
```

In the app: click **Refresh all** to pull data, then use the **Partner Finder** and
**Tournament Board** tabs. Each tournament card has a "Who near me is NOT signed up?"
expander — that's the core feature.

## Partner Finder

A sortable table of DUPR players near you in your rating band, with:

- **Activity filter (on by default):** only players with a recorded DUPR match in
  the last year are shown. The DUPR fetch looks up each player's most recent match
  (cached; re-checked every ~2 weeks). Toggle **Active only** off to see everyone;
  "inactive" = confirmed no match in 12 months, "?" = not yet looked up. Editable via
  `ACTIVITY_LOOKBACK_DAYS` in `config.py`.
- **Research / contact links** per player. Emails are NOT available through DUPR —
  verified against the live API: it returns only a `verifiedEmail: true/false` flag
  for other players, never the address. So the links are ordered by hit rate:
  - **DUPR↗** — direct link to their DUPR profile
  - **G🔍** — general Google search: `"Name" pickleball <their city> AZ` (best first
    stop; surfaces Facebook profiles, league pages, club rosters, news)
  - **IG🔍** — Google search scoped to their Instagram (`site:instagram.com`)
  - **YT🔍** — YouTube search for "<name> arizona pickleball"
  - plus any Instagram handle / email / phone you add manually
- **DUPR profile photo** shown as an avatar next to each name (~1/3 of players have
  one) — use it to confirm you found the right person on Facebook/Instagram.
- **Last match** column shows each player's most recent DUPR match date.

The UI uses a dark neon/esports theme (Rajdhani + Share Tech Mono, cyan/pink/lime
accents); it renders fine offline (system-font fallback).

## Combined-rating eligibility (partner finder for cash divisions)

Every tournament card has a **"Who near me is NOT signed up? (eligible partners)"**
expander. Pick a combined cap (8.5 / 9 / 9.5 / 10) — or, for Second Serve events,
it auto-loads the event's own cap — and it lists nearby DUPR players who aren't
registered and checks whether pairing with *you* fits under the cap.

The math (matches AZ cash-game rules): each player's DUPR is rounded to 1 decimal,
females get a 0.5 rating allowance, 50+ players get a 0.5 allowance, and the two
**stack** (a 50+ female gets 1.0). Example at a 9.5 cap with you at 4.9:

| Partner | Max eligible DUPR |
|---|---|
| Male, under 50 | 4.6 |
| Female, under 50 | 5.1 |
| Male, 50+ | 5.1 |
| Female, 50+ | 5.6 |

Each candidate shows the computed combined rating (✓/✗), the allowance applied, and
their gender/age. **Second Serve events use the exact per-event reduction values from
their API** (which vary — some use 0.25, tiered age thresholds, or no reduction at
all) instead of the 0.5 defaults. All defaults are editable in `config.py`
(`COMBINED_*`). Note: AZ Cash events don't publish rosters, so "not signed up" there
means everyone in range is shown; Second Serve events filter out actual registrants.

## Credentials (.env)

The no-login sources work immediately. To enable the login-gated sources, put **your
own** account credentials in `.env` (git-ignored, never sent anywhere but the source's
own login endpoint):

| Source | .env keys | What it adds |
|---|---|---|
| DUPR | `DUPR_EMAIL` / `DUPR_PASSWORD` | Individual player ratings + AZ player directory within your rating window |
| PickleMoneyBall | `PMB_EMAIL` / `PMB_PASSWORD` | Your own per-event sign-up + partner (events themselves load without login) |
| APP / PickleballDen | `PBDEN_EMAIL` / `PBDEN_PASSWORD` | APP registrant lists *(deferred — see below)* |

Leave any blank to skip that source. **Note:** DUPR's Terms of Service restrict
automated access even when logged in; using this is your call as the account holder.
The fetchers self-throttle (default 2s/request/host).

## Data sources & how they're pulled

| Source | Method | Login | Rosters |
|---|---|---|---|
| **Second Serve** | Open JSON API | no | ✅ public (names + combined DUPR) |
| **AZ Cash Tournaments** | schema.org JSON-LD scrape | no | — (aggregator; links out) |
| **MatchPoint Open** | Shopify `products.json` | no | — (registers via PickleballTournaments) |
| **PPA Challenger** | server-rendered HTML | no | — (registers via PickleballTournaments) |
| **APP Tour** | server-rendered HTML (schedule) | no | ⏳ see below |
| **DUPR** | authenticated JSON API | yes | player ratings/directory |
| **PickleMoneyBall** | VSQ API (events public; sign-ups authed) | optional | your own sign-up only (no public all-registrants list) |
| **APP / PickleballDen** | — | yes | ⏳ deferred |

**APP / PickleballDen deferred:** PickleballDen is a Vaadin Flow app (session-cookie
auth, server-rendered UIDL protocol) with no clean JSON API, so registrant scraping
needs a headless browser. The APP *schedule* is captured with registration deep links
for manual roster review. Cleaner future path: request an `api.pickleballden.com` API
key. Same for a possible DUPR/pickleball.com official API key.

## What's where

```
app/
  config.py         your profile, target metros, rating window, division filters
  db.py store.py    SQLite schema + dedupe/upsert (respects manual overrides)
  geo.py geocode.py distance + static city/venue coordinates
  main.py           FastAPI routes + background refresh
  fetchers/         one module per source (auto-register on import)
  static/           the dashboard (vanilla HTML/CSS/JS, no build step)
run.py              launcher
.env                your credentials (create from .env.example)
```

Data lives in `app/data/azpb.db`. Manually added/edited players and tournaments are
flagged `manual_override` and are never clobbered by a refresh.

## Refresh cadence

Re-run **Refresh all** whenever you want fresh data (schedules and ratings change).
Nothing is scheduled automatically — it's on-demand from the UI.
