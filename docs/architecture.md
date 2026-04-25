# Architecture

## Overview

OpenFraudMonitoring is a 5-service system that collects browser fingerprints and behavioral data, stores them in PostgreSQL, evaluates detection rules asynchronously via Redis, and presents results in a React dashboard.

```
┌─────────────┐     ┌─────────────┐     ┌───────────┐
│  Browser    │────▶│  Backend    │────▶│ PostgreSQL│
│ fingerprint │     │  (Flask)    │     └───────────┘
│   .js       │     │             │────▶┌───────────┐     ┌──────────┐
└─────────────┘     │  :5000      │     │   Redis   │────▶│  Worker  │
                    └─────────────┘     └───────────┘     └──────────┘
                          ▲
┌─────────────┐           │
│  Dashboard  │───────────┘
│  (React)    │
│  :3000      │
└─────────────┘
```

## Services

| Service | Image/Stack | Purpose |
|---------|------------|---------|
| `backend` | Python 3.11 / Flask | REST API — receives fingerprints and heartbeats, serves data to the dashboard |
| `worker` | Same image, `python worker.py` | Consumes events from Redis, evaluates detection rules, updates risk scores |
| `frontend` | React / Vite / nginx | Dashboard UI |
| `db` | PostgreSQL 16 | Persistent storage |
| `redis` | Redis 7 | Event queue between backend and worker |

## Data Flow

### 1. Collection

A browser loads `fingerprint.js`. On page load, the client:
1. Collects device signals (navigator, screen, WebGL, canvas, audio, bot signals, etc.)
2. Generates a deterministic `deviceID` from the fingerprint
3. Sends the full fingerprint to `POST /api/collect`

Every 30 seconds, a heartbeat with behavioral data (mouse, clicks, keys, scrolls, copy/paste) is sent to `POST /api/heartbeat`.

### 2. Ingestion (Backend)

On `/api/collect`:
- Find or create a `Session` by `device_id`
- Run the built-in `RiskAnalyzer` (bot signals, hardware anomalies, etc.)
- Store the raw fingerprint as JSONB + denormalized columns for filtering
- Push an event to Redis: `{"session_id": 42, "type": "fingerprint"}`

On `/api/heartbeat`:
- Look up the session via the browser session ID
- Store a `Heartbeat` row with denormalized behavior counts + raw JSONB
- Push a Redis event

### 3. Rule Evaluation (Worker)

The worker runs two loops concurrently:

- **Realtime loop** — `BRPOP` on `ofm:events`. For each event, evaluates all enabled `realtime` rules against the triggering session. If a rule matches, a `RuleMatch` row is created and the session's `risk_score` is adjusted by `score_modifier`.

- **Periodic loop** — every `PERIODIC_INTERVAL_SECONDS` (default 60s), evaluates all `periodic` rules against the full session table.

### 4. Dashboard

The React frontend polls `GET /api/sessions` every 10 seconds. It can pass a `?filters=[...]` query parameter to apply filters server-side. The filter builder fetches the field schema from `GET /api/schema` and autocomplete suggestions from `GET /api/suggest`.

## Database Schema

```
sessions
  ├── id, device_id, risk_score, flags (JSONB), client_ip
  ├── first_seen, last_seen, created_at, updated_at
  │
  ├──< fingerprints
  │     ├── id, session_id, timestamp, data (JSONB)
  │     └── user_agent, platform, language, operating_system, timezone,
  │         public_ip, webgl_vendor, webgl_renderer, screen_width,
  │         screen_height, color_depth, hardware_concurrency,
  │         device_memory, is_mobile, is_workstation, has_webdriver
  │
  ├──< heartbeats
  │     ├── id, session_id, timestamp, url
  │     ├── mouse_moves, clicks, keydowns, touches, scrolls,
  │     │   copy_pastes, navigation_events
  │     └── raw_behavior (JSONB)
  │
  ├──< session_urls (session_id, url — unique pair)
  └──< browser_sessions (session_id, browser_session_id — unique)

rules
  ├── id, name, description, enabled, rule_type, logic
  ├── conditions (JSONB), score_modifier, period_seconds
  └──< rule_matches (rule_id, session_id, score_change, matched_at)
```

Fingerprint data is stored both as raw JSONB (for full detail) and as denormalized columns (for indexed queries and filtering).

## Folder Structure

```
backend/
  config.py              # Centralized env-based config
  app.py                 # Flask app factory, route registration
  worker.py              # Redis consumer + periodic evaluator
  services/
    database.py          # SQLAlchemy setup
    event_queue.py       # Redis queue helpers
    schema.py            # Schema registry (filterable fields)
  models/
    session.py           # Session model
    fingerprint.py       # Fingerprint model + extract_fields()
    heartbeat.py         # Heartbeat model + to_summary()
    rule.py              # Rule + RuleMatch models
    associations.py      # SessionURL, BrowserSession
  routes/
    collect.py           # POST /api/collect
    heartbeat.py         # POST /api/heartbeat
    sessions.py          # GET /api/sessions, GET /api/sessions/<id>
    stats.py             # GET /api/stats
    rules.py             # CRUD /api/rules
    filters.py           # GET /api/schema, GET /api/suggest
  rules/
    engine.py            # Filter → SQLAlchemy query builder
  analysis/
    risk.py              # Built-in risk scoring (bot detection, etc.)
  utils/
    __init__.py          # extract_behavior_summary()

client/
  src/
    config.js            # Endpoints + OFM_SERVER_URL
    index.js             # Entry point
    collect.js           # Fingerprint assembly
    heartbeat.js         # Periodic behavioral snapshots
    send.js              # Beacon/fetch transport
    collectors/          # One file per signal category

frontend/
  src/
    App.jsx              # Router
    Dashboard.jsx        # Session list + stats + filter builder
    SessionDetail.jsx    # Single session deep dive
    FilterBuilder.jsx    # UI for composing filter conditions
    api.js               # All API calls
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/collect` | Receive initial fingerprint |
| POST | `/api/heartbeat` | Receive behavioral update |
| GET | `/api/sessions` | List sessions (supports `?filters=[...]`) |
| GET | `/api/sessions/<device_id>` | Session detail |
| GET | `/api/stats` | Aggregate statistics |
| GET | `/api/schema` | Filterable field definitions |
| GET | `/api/suggest?field=x&q=y` | Autocomplete values for a field |
| GET | `/api/rules` | List all rules |
| POST | `/api/rules` | Create a rule |
| PUT | `/api/rules/<id>` | Update a rule |
| DELETE | `/api/rules/<id>` | Delete a rule |
| GET | `/fingerprint.js` | Client script |

## Built-in Risk Scoring

`analysis/risk.py` runs on every `/api/collect` and assigns a base score (0–100):

| Signal | Points |
|--------|--------|
| ChromeDriver props detected | +45 |
| WebDriver detected | +40 |
| PhantomJS detected | +40 |
| Selenium/Puppeteer/Nightmare | +35 |
| Native function spoofed | +30 |
| Zero screen dimensions | +25 |
| Empty languages | +20 |
| Zero CPU cores | +20 |
| Zero device memory | +15 |
| No plugins | +15 |
| No canvas | +10 |
| No WebGL | +10 |

Custom rules (see [rules.md](rules.md)) add or subtract from this base score.
