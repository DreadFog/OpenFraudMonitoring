# Architecture

## Overview

OpenFraudMonitoring is a multi-service system that collects browser fingerprints and behavioral data, stores them in PostgreSQL, evaluates detection rules asynchronously via Redis, enriches observables through pluggable connectors via RabbitMQ, and presents results in a React dashboard.

```
┌─────────────┐     ┌─────────────┐     ┌───────────┐
│  Browser    │────▶│  Backend    │────▶│ PostgreSQL│
│ fingerprint │     │  (Flask)    │     │  sessions │
│   .js       │     │             │     │  STIX     │
└─────────────┘     │  :5000      │     └───────────┘
                    │             │────▶┌───────────┐     ┌──────────┐
                    │             │     │   Redis   │────▶│  Worker  │
                    └──────┬──────┘     └───────────┘     └──────────┘
                           │
                    ┌──────┴──────┐     ┌───────────┐
                    │  RabbitMQ   │◀───▶│Connectors │
                    │  ofm.intel  │     │ (IPinfo,  │
                    └─────────────┘     │  OpenCTI) │
                           ▲            └───────────┘
┌─────────────┐            │
│  Dashboard  │────────────┘
│  (React)    │
│  :3000      │
└─────────────┘
```

## Services

| Service | Image/Stack | Purpose |
|---------|------------|---------|
| `backend` | Python 3.11 / Flask | REST API — receives fingerprints and heartbeats, serves data to the dashboard, routes enrichment requests, JWT/API-token auth (RBAC), TAXII 2.1 server |
| `worker` | Same image, `python worker.py` | Consumes events from Redis, evaluates detection rules, updates risk scores, ingests STIX bundles from connectors |
| `frontend` | React / Vite / nginx | Dashboard UI with customizable widgets, intelligence browser, logging page |
| `db` | PostgreSQL 16 | Persistent storage (sessions + STIX intel) |
| `redis` | Redis 7 | Event queue between backend and worker, connector heartbeats and metadata |
| `rabbitmq` | RabbitMQ 3.13 | Message bus for connector intel request/response |
| `connector-*` | Python 3.11 | Pluggable enrichment connectors (see [connectors.md](connectors.md)) |

## Authentication & Authorization

All dashboard and admin endpoints require authentication; ingestion endpoints (`/api/initial`, `/api/heartbeat`, `/api/behavioral_event`) are public.

- **Login** (`POST /api/auth/login`) returns a short-lived **JWT** (HS256, signed with `JWT_SECRET`, expiry `JWT_EXPIRY_HOURS`, default 24h).
- **API tokens** (format `ofm_<32 hex>`, stored SHA-256 hashed) provide non-interactive access. Both JWTs and API tokens are sent as `Authorization: Bearer <token>`.
- **Roles**: `user`, `admin`, `connector`. Connector accounts have no password and are used to attribute ingested intel to its source.
- Enforced by the `@require_auth` and `@require_role(...)` decorators in `services/auth.py`.
- A default admin is seeded on startup from `OFM_ADMIN_USERNAME` / `OFM_ADMIN_PASSWORD`. `OFM_ADMIN_TOKEN` is the shared token connectors use to call `POST /api/intel/ingest`.

## Data Flow

### 1. Collection

A browser loads `ofm.js`. On page load, the client:
1. Runs FPScanner to collect 35 signal categories and 21 bot detection rules
2. FPScanner generates a deterministic `fsid` (JA4-inspired fingerprint ID)
3. The encrypted fingerprint is sent to `POST /api/initial`

Every 30 seconds, a heartbeat with low-signal behavioral data (mouse, clicks, keys, scrolls) is sent to `POST /api/heartbeat`. High-signal events (button clicks, form submits, copy/paste) are sent immediately to `POST /api/behavioral_event`.

### 2. Ingestion (Backend)

On `/api/initial`:
- Decrypt the FPScanner encrypted payload (XOR + Base64)
- Find or create a `Session` by `fsid`
- Store the raw fingerprint as JSONB + denormalized columns for filtering
- Create STIX observables for the client IP and user-agent (deduplicating by value)
- Link the session to its IP and user-agent STIX observables
- Push an event to Redis: `{"session_id": 42, "type": "fingerprint"}`
- Auto-trigger any connectors in `auto` or `both` mode

On `/api/heartbeat`:
- Look up the session via the browser session ID
- Store a `Heartbeat` row with denormalized behavior counts + raw JSONB
- Push a Redis event

On `/api/behavioral_event`:
- Store a `BehavioralEvent` row (`event_type`, `url`, `data` JSONB) linked to the session. These power the `behavior_*` filter/rule fields (see [filters.md](filters.md)).

### 3. Rule Evaluation (Worker)

The worker runs two loops concurrently:

- **Realtime loop** — `BRPOP` on `ofm:events`. For each event, evaluates all enabled `realtime` rules against the triggering session. If a rule matches, a `RuleMatch` row is created and the session's `risk_score` is adjusted by `score_modifier`.

- **Periodic loop** — every `PERIODIC_INTERVAL_SECONDS` (default 60s), evaluates all `periodic` rules against the full session table.

### 4. Intelligence Enrichment

When a new fingerprint is collected, the backend auto-publishes enrichment requests to connectors running in `auto` or `both` mode. Connectors can also be triggered manually from the Intelligence page via the "Enrich" button.

```
Backend  ──publish──▶  ofm.intel exchange  ──route──▶  intel.requests.<connector>
                                                            │
                                                       connector handler
                                                            │
Worker   ◀──consume──  intel.responses     ◀──publish──────┘
   │
   └──▶ ingest STIX bundle into PostgreSQL
```

The worker consumes response messages from the `intel.responses` queue and persists the STIX objects (observables, SDOs, relationships) into per-type tables.

### 5. Dashboard

The React frontend polls `GET /api/sessions` every 10 seconds. It can pass a `?filters=[...]` query parameter to apply filters server-side. The filter builder fetches the field schema from `GET /api/schema` and autocomplete suggestions from `GET /api/suggest`.

The Intelligence page allows browsing all STIX entity types, searching by value, viewing relationships, navigating between related entities, and triggering enrichment.

## Database Schema

### Session Tables

```
sessions
  ├── id, fsid, risk_score, flags (JSONB), client_ip
  ├── authenticated (bool), domains (JSONB)   ← monitored-domain auth cookie + URL hosts
  ├── ip_observable_type, ip_observable_id    ← FK to STIX IP table
  ├── user_agent_observable_id                ← FK to STIX user-agent table
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
  ├──< behavioral_events
  │     └── id, session_id, timestamp, event_type, url, data (JSONB)
  ├──< beh_auth_attempt   ← server-generated login-form matches
  │     └── id, session_id, domain_config_id, timestamp, url,
  │         action, method, matched_field_names (JSONB)
  ├──< session_urls (session_id, url — unique pair)
  └──< browser_sessions (session_id, browser_session_id — unique)

rules
  ├── id, name, description, enabled, rule_type, logic
  ├── conditions (JSONB), score_modifier, period_seconds
  └──< rule_matches (rule_id, session_id, score_change, matched_at)

dashboards
  ├── id, name, widgets (JSONB), created_at, updated_at

users
  ├── id, username, password_hash (nullable), role (user|admin|connector)
  ├── is_active, created_at, updated_at
  └──< api_tokens (token_hash [SHA-256], token_prefix, name, expires_at)

allowed_origins   ← dynamic CORS allowlist (origin, enabled)
domain_configs    ← monitored domains (domain, auth_cookie_name,
                    form_action, form_method, form_field_names, active)
taxii_feeds       ← published TAXII 2.1 collections (uuid, name, filters)
```

### STIX 2.1 Tables

All STIX entity tables share a common schema:

| Column | Type | Description |
|--------|------|-------------|
| `id` | int | Local primary key |
| `stix_id` | string | Canonical STIX 2.1 ID (e.g. `ipv4-addr--<uuid>`), unique |
| `value` | string | Human-readable value, indexed |
| `created_at_platform` | datetime | When first seen on this platform |
| `last_refreshed_at` | datetime | When last enriched from a connector |
| `decayed` | bool | True once data is older than `INTEL_DECAY_DAYS` |
| `raw` | JSONB | Full STIX object |

```
stix_ipv4_addr          ← IP address observables (SCO)
stix_ipv6_addr          ← IP address observables (SCO)
stix_user_agent         ← User-agent observables (custom SCO)
stix_autonomous_system  ← AS number observables (SCO)
stix_country            ← Location SDOs scoped to country
stix_indicator          ← Indicator SDOs (patterns)
stix_malware            ← Malware SDOs
stix_campaign           ← Campaign SDOs
stix_intrusion_set      ← Intrusion Set SDOs

stix_relationship       ← SROs linking any two STIX objects
  ├── stix_id, relationship_type
  ├── source_ref, target_ref    ← STIX IDs (cross-table references)
  ├── start_time, stop_time
  └── decayed
```

STIX IDs are deterministic (UUIDv5 with OASIS namespace + canonical JSON), ensuring deduplication across connector runs.

## Redis Keys

| Key pattern | Purpose |
|-------------|---------|
| `ofm:events` | Event queue (backend → worker) |
| `ofm:logs` | Centralized log entries (WARNING+) |
| `ofm:connector:<name>:heartbeat` | Connector liveness (TTL 30s) |
| `ofm:connector:<name>:mode` | Connector mode (manual/auto/both) |
| `ofm:connector:<name>:type` | Connector type (enricher/importer) |
| `ofm:connector:<name>:scope` | JSON array of STIX types the connector handles |

## Folder Structure

```
backend/
  init/config.py         # Centralized env-based config
  app.py                 # Flask app factory, dynamic CORS, route registration
  worker.py              # Redis consumer + periodic evaluator + STIX ingest
  services/
    database.py          # SQLAlchemy setup
    auth.py              # Password hashing, JWT, API tokens, auth decorators
    event_queue.py       # Redis queue helpers
    schema.py            # Schema registry (filterable fields)
    mq.py                # RabbitMQ publish helpers
    intel_ingest.py      # STIX bundle → database ingestion
    stix_store.py        # get_or_create helpers for STIX entities
    stix_filters.py      # STIX filtering for TAXII feeds
    cors_origins.py      # Dynamic CORS origin validation
    domains.py           # Monitored-domain matching (auth cookie, login form)
    log_shipper.py       # Centralized log shipping to Redis
  models/
    session.py           # Session model (with STIX observable FKs)
    fingerprint.py       # Fingerprint model + extract_fields()
    heartbeat.py         # Heartbeat model + to_summary()
    behavioral_event.py  # BehavioralEvent model (high-signal events)
    rule.py              # Rule + RuleMatch models
    associations.py      # SessionURL, BrowserSession
    dashboard.py         # Dashboard model (widget layouts)
    user.py              # User + ApiToken models (auth/RBAC)
    cors.py              # AllowedOrigin model (dynamic CORS)
    domain.py            # DomainConfig model (monitored domains)
    taxii_feed.py        # TaxiiFeed model (published collections)
    stix.py              # All STIX 2.1 models (9 entity types + relationship)
  routes/
    auth.py              # /api/auth — login, profile, tokens, user CRUD
    collect.py           # POST /api/initial (creates STIX observables)
    heartbeat.py         # POST /api/heartbeat
    behavioral_event.py  # POST /api/behavioral_event
    sessions.py          # GET/DELETE /api/sessions
    stats.py             # GET /api/stats
    rules.py             # CRUD /api/rules
    filters.py           # GET /api/schema, GET /api/suggest
    intel.py             # Intelligence endpoints (entity lookup, enrichment)
    connectors.py        # Connector status, enricher listing, logs
    dashboards.py        # CRUD /api/dashboards
    cors.py              # /api/admin/cors — CORS allowlist management
    domains.py           # /api/admin/domains — monitored domains + JSON import/export
    taxii.py             # /taxii2 — TAXII 2.1 server
    taxii_feeds.py       # /api/taxii-feeds — feed management
  rules/
    engine.py            # Filter → SQLAlchemy query builder
    defaults/            # Built-in detection rules (JSON)
  filters/               # Behavioral filter registry + IP/domain filters + suggestions
  analysis/
    risk.py              # Built-in risk scoring (bot detection)

client/
  src/
    config.js            # Endpoints + OFM_SERVER_URL
    index.js             # Entry point — FPScanner + extensions
    send.js              # Beacon/fetch transport
    extensions/          # Extension registry (behavioral tracking)

connectors/
  base/
    connector_base/      # Shared library (config, runner, log shipper)
  ipinfo/                # IPinfo Lite enricher (IP → AS + country)
  opencti/               # OpenCTI enricher (IP/UA → indicators, malware)

frontend/
  src/
    api.js               # All API calls
    App.jsx              # Router
    pages/
      Dashboard/         # Session list + custom widgets + filters
      SessionDetail/     # Single session deep dive
      Intelligence/      # STIX entity browser + enrichment
      Logging/           # Connector health + system logs
      Landing/           # Welcome page
      Login/             # Authentication
      Profile/           # Password change + API token management
      Users/             # Admin user management
      Rules/             # Admin rule management
      Exports/           # TAXII feed / data exports
    components/
      FilterBuilder/     # Composable filter conditions
      WidgetWizard/      # Widget creation wizard
      NavHeader/         # Navigation bar
      IpIntelPopover/    # IP intel popup (lens icon)
```

## API Endpoints

All `/api/*` endpoints except the ingestion ones require an `Authorization: Bearer <token>` header (JWT or API token). Admin-only endpoints additionally require the `admin` role.

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Log in, returns a JWT |
| GET | `/api/auth/me` | Current user profile + token metadata |
| PUT | `/api/auth/password` | Change own password |
| GET | `/api/auth/tokens` | List own API tokens |
| POST | `/api/auth/tokens` | Create an API token (raw value returned once) |
| DELETE | `/api/auth/tokens/<id>` | Revoke an API token |
| GET | `/api/auth/users` | List users (admin) |
| POST | `/api/auth/users` | Create user (admin) |
| PUT | `/api/auth/users/<id>` | Update user (admin) |
| DELETE | `/api/auth/users/<id>` | Delete user (admin) |
| POST | `/api/auth/users/<id>/tokens` | Issue a token for another user (admin) |

### Session & Collection

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/initial` | Receive initial fingerprint (public) |
| POST | `/api/heartbeat` | Receive behavioral update (public) |
| POST | `/api/behavioral_event` | Receive a high-signal behavioral event (public) |
| GET | `/api/sessions` | List sessions (supports `?filters=[...]`) |
| GET | `/api/sessions/<fsid>` | Session detail |
| DELETE | `/api/sessions/<fsid>` | Delete session and all child data |
| GET | `/api/stats` | Aggregate statistics |
| GET | `/api/schema` | Filterable field definitions |
| GET | `/api/suggest?field=x&q=y` | Autocomplete values for a field |
| GET | `/ofm.js` | Client collection script |

### Rules

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/rules` | List all rules |
| POST | `/api/rules` | Create a rule |
| PUT | `/api/rules/<id>` | Update a rule |
| DELETE | `/api/rules/<id>` | Delete a rule |

### Dashboards

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboards` | List saved dashboards |
| POST | `/api/dashboards` | Create a dashboard |
| PUT | `/api/dashboards/<id>` | Update a dashboard |
| DELETE | `/api/dashboards/<id>` | Delete a dashboard |
| POST | `/api/widget-data` | Fetch data for a widget configuration |

### Intelligence

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/intel/types` | List entity types with counts |
| GET | `/api/intel/entities?type=&limit=` | List latest entities of a type |
| GET | `/api/intel/entity?type=&value=` | Full entity detail (relationships, AS, country, session count) |
| GET | `/api/intel/filter-schema?type=` | Filterable field schema for an entity type |
| GET | `/api/intel/ip/<value>` | IP-specific lookup (used by the popover) |
| POST | `/api/intel/lookup` | Enqueue enrichment request to a connector |
| POST | `/api/intel/ingest` | Direct STIX bundle ingest (connector auth) |

### Connectors

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/connectors/status` | All connector status (health, mode, type, scope, queue depth) |
| GET | `/api/connectors/enrichers?entity_type=` | List healthy enrichers for an entity type |
| GET | `/api/connectors/logs?tail=100` | Recent system log entries |

### Admin — CORS Allowlist

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/cors/origins` | List allowed origins |
| POST | `/api/admin/cors/origins` | Add an allowed origin |
| DELETE | `/api/admin/cors/origins/<id>` | Remove an origin |
| PATCH | `/api/admin/cors/origins/<id>/toggle` | Enable/disable an origin |

### Admin — Monitored Domains

See [Monitored Domains](domains.md).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/domains` | List domain configurations |
| POST | `/api/admin/domains` | Create a domain configuration |
| PUT | `/api/admin/domains/<id>` | Update a domain configuration |
| DELETE | `/api/admin/domains/<id>` | Delete a domain configuration |
| GET | `/api/admin/domains/export` | Download all configurations as JSON |
| POST | `/api/admin/domains/import` | Upsert configurations from JSON |

### TAXII 2.1

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/taxii-feeds` | List published feeds |
| GET | `/api/taxii-feeds/<id>` | Feed detail |
| POST | `/api/taxii-feeds` | Create a feed |
| PUT | `/api/taxii-feeds/<id>` | Update a feed |
| DELETE | `/api/taxii-feeds/<id>` | Delete a feed |
| GET | `/taxii2/` | TAXII discovery |
| GET | `/taxii2/default/` | API root |
| GET | `/taxii2/default/collections/` | List collections |
| GET | `/taxii2/default/collections/<id>/` | Collection metadata |
| GET | `/taxii2/default/collections/<id>/objects/` | STIX objects in a collection |

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
