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
1. Runs FPScanner to collect 35 signal categories and 21 bot detection rules
2. FPScanner generates a deterministic `fsid` (JA4-inspired fingerprint ID)
3. The encrypted fingerprint + OFM extension data (IP, behavior) is sent to `POST /api/collect`

Every 30 seconds, a heartbeat with behavioral data (mouse, clicks, keys, scrolls, copy/paste) is sent to `POST /api/heartbeat`.

### 2. Ingestion (Backend)

On `/api/collect`:
- Decrypt the FPScanner encrypted payload (XOR + Base64)
- Find or create a `Session` by `fsid` (FPScanner's JA4-inspired fingerprint ID)
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
  ├── id, fsid, risk_score, flags (JSONB), client_ip
  ├── first_seen, last_seen, created_at, updated_at
  │
  ├──< fingerprints
  │     ├── id, session_id, timestamp, data (JSONB)
  │     ├── fsid, fast_bot_detection, url
  │     ├── automation_* (webdriver, selenium, cdp, playwright, ...)
  │     ├── device_* (cpu_count, memory, platform, screen_resolution_*, ...)
  │     ├── browser_* (user_agent, features_*, plugins_*, extensions_*, ...)
  │     ├── graphics_* (webgl_*, webgpu_*, canvas_*)
  │     ├── codecs_*, locale_*, contexts_*
  │     └── det_* (21 FPScanner detection booleans)
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
    index.js             # Entry point — orchestrates FPScanner + extensions
    send.js              # Beacon/fetch transport
    extensions/
      index.js           # Extension registry
      behavior.js        # Behavioral tracking (mouse, clicks, keys, scrolls)
      ip.js              # Public IP collection via external API

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
| GET | `/api/sessions/<fsid>` | Session detail |
| GET | `/api/stats` | Aggregate statistics |
| GET | `/api/schema` | Filterable field definitions |
| GET | `/api/suggest?field=x&q=y` | Autocomplete values for a field |
| GET | `/api/rules` | List all rules |
| POST | `/api/rules` | Create a rule |
| PUT | `/api/rules/<id>` | Update a rule |
| DELETE | `/api/rules/<id>` | Delete a rule |
| GET | `/fingerprint.js` | Client script |

## Built-in Risk Scoring

`analysis/risk.py` uses FPScanner's 21 built-in detection rules (from `fastBotDetectionDetails`).
Each detection has a severity that maps to score points:

| Severity | Points |
|----------|--------|
| high     | +15    |
| medium   | +8     |
| low      | +3     |

Detections include: hasWebdriver, hasCDP, hasPlaywright, hasSeleniumProperty, hasBotUserAgent,
hasGPUMismatch, hasPlatformMismatch, hasSwiftshaderRenderer, hasUTCTimezone, and more.

Custom rules (see [rules.md](rules.md)) add or subtract from this base score.
