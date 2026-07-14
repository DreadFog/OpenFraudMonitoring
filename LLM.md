# LLM.md — OpenFraudMonitoring

Dense technical reference for LLMs. Self-hosted browser fingerprinting, behavioral analysis, bot detection, and STIX threat-intel platform. One `<script src="/ofm.js">` tag collects fingerprints + behavior; a React dashboard visualizes and scores sessions.

## Stack

- **Backend**: Python 3.11, Flask 2.3, Flask-SQLAlchemy 3.1 / SQLAlchemy 2.0, Flask-Bcrypt, PyJWT, pika (RabbitMQ), redis-py, stix2 3.0.
- **DB**: PostgreSQL 16 (JSONB + denormalized columns). Schema created via `create_all()` — **no migration tool**; column additions require manual `ALTER TABLE` / DB recreate.
- **Queues**: Redis 7 (event queue backend→worker, logs, connector metadata), RabbitMQ 3.13 (connector intel request/response).
- **Frontend**: React 18, react-router-dom 6, react-grid-layout 2, Vite 5, served by nginx.
- **Client** (`client/`): Vite bundle wrapping `fpscanner`, emits `ofm.js`. Version 3.x.
- **fpscanner/**: standalone TS fingerprinting + bot-detection lib (Vite build, Playwright tests, obfuscation, XOR+Base64 payload encryption). 35+ signal categories, 21 bot detections.

## Services (docker-compose.yml)

| Service | Stack | Role |
|---|---|---|
| `backend` | Flask, port 5000 | REST API, ingestion, serves `/ofm.js`, TAXII 2.1 server |
| `worker` | `python worker.py` | Realtime + periodic rule eval, STIX bundle ingest |
| `frontend` | React/Vite/nginx, port 30000→3000 | Dashboard UI |
| `db` | postgres:16-alpine | Persistence |
| `redis` | redis:7-alpine | Event queue, logs, connector metadata |
| `rabbitmq` | rabbitmq:3.13-management | Connector message bus |
| `connector-ipinfo`, `connector-opencti` | Python 3.11 | Enrichment connectors |

`docker-compose.test.yml` exists for tests.

## Data flow

1. Browser loads `ofm.js` → fpscanner runs, generates deterministic `fsid` → encrypted payload → `POST /api/initial`.
2. Backend decrypts (XOR+Base64, key=`FPSCANNER_KEY`), upserts `Session` by `fsid`, stores raw fingerprint (JSONB) + denormalized `fingerprints` columns, creates/links STIX IP + user-agent observables, pushes `{"session_id":N,"type":"fingerprint"}` to Redis `ofm:events`, auto-triggers `auto`/`both` connectors.
3. Every 30s: behavioral heartbeat → `POST /api/heartbeat`. High-signal events (button click, form submit, copy/paste) → `POST /api/behavioral_event` (stored in `behavioral_events`).
4. Worker: realtime loop `BRPOP ofm:events` evaluates enabled `realtime` rules on the triggering session; periodic loop (every `PERIODIC_INTERVAL_SECONDS`) evaluates `periodic` rules over all sessions. Matches create `RuleMatch`, append rule name to `session.flags`, add `score_modifier` (capped 100).
5. Connectors consume `intel.requests.<name>` (exchange `ofm.intel`), call external API, publish STIX bundle to `intel.responses`; worker `ingest_bundle()` persists per-type STIX tables.
6. Frontend polls `GET /api/sessions` (~10s) with `?filters=[...]`.

## Backend layout (`backend/`)

- `app.py` — Flask app, dynamic CORS via `after_request` (origins from DB), registers routes, seeds rules + admin.
- `worker.py` — 3 threads: realtime (main), periodic, intel-response consumer.
- `init/config.py` — `Config` from env. `init/generate_schema.py` + `_generated_schema.py` — schema autogen from fpscanner `types.ts`. `init/seed_users.py`, `init/seed_rules.py`.
- `models/`: `session.py` (Session + STIX observable FKs), `fingerprint.py` (`extract_fields()` denormalizes JSONB), `heartbeat.py`, `behavioral_event.py`, `rule.py` (Rule + RuleMatch), `associations.py` (SessionURL, BrowserSession), `dashboard.py`, `user.py` (User + ApiToken; `settings` JSONB for per-user prefs), `app_setting.py` (AppSetting = global key/value), `cors.py` (AllowedOrigin), `taxii_feed.py` (TaxiiFeed), `stix.py` (9 entity models + Relationship).
- `services/`: `database.py` (+`_apply_column_upgrades` adds `users.settings` — no migration tool), `auth.py` (hash/JWT/API-token/decorators), `event_queue.py` (Redis), `mq.py` (RabbitMQ publish/consume), `schema.py` (`SCHEMA_FIELDS` registry), `intel_ingest.py` (`ingest_bundle`), `stix_store.py` (get_or_create), `stix_filters.py`, `cors_origins.py` (`dynamic_origin`), `log_shipper.py` (ships WARNING+ to Redis `ofm:logs`), `settings.py` (user/global settings defaults+merge), `graph.py` (graph node/edge builders, expansions, `compute_links`).
- `rules/engine.py` — `build_condition`, `build_session_query` (fingerprint conditions wrapped in `EXISTS`); `evaluate_rule`. `rules/defaults/*.json` auto-seeded.
- `analysis/risk.py` — base risk score from fpscanner `fastBotDetectionDetails` severity: high=+15, medium=+8, low=+3.
- `filters/` — behavior filter registry + IP filters + autocomplete suggestions.

## Auth & RBAC (`services/auth.py`, `routes/auth.py`)

- Login → short-lived **JWT** (HS256, `JWT_SECRET`, `JWT_EXPIRY_HOURS`=24). `Authorization: Bearer <jwt>`.
- **API tokens** format `ofm_<32hex>`, stored SHA-256 hashed + 12-char prefix; sent as Bearer too. Self-service under `/api/auth/tokens`.
- Roles: `user | admin | connector` (connector accounts have null password; used for intel source tracking).
- Decorators: `@require_auth` (sets `g.current_user`), `@require_role(*roles)`.
- Admin bootstrap: `OFM_ADMIN_USERNAME`/`OFM_ADMIN_PASSWORD` seeded on startup. `OFM_ADMIN_TOKEN` = shared connector→backend token.

## API endpoints (prefix → route)

**Auth** `/api/auth`: `POST /login`, `GET /me`, `PUT /password`, `GET|POST /tokens`, `DELETE /tokens/<id>`, `GET|POST /users` (admin), `PUT|DELETE /users/<id>` (admin), `POST /users/<id>/tokens` (admin).

**Collection** `/api`: `POST /initial`, `POST /heartbeat`, `POST /behavioral_event`.

**Sessions** `/api`: `GET /sessions?filters=[...]`, `GET /sessions/<fsid>`, `DELETE /sessions/<fsid>`. `GET /stats`.

**Filters** `/api`: `GET /schema`, `GET /suggest?field=&q=`.

**Rules** `/api` (admin): `GET|POST /rules`, `PUT|DELETE /rules/<id>`.

**Dashboards** `/api`: `GET|POST /dashboards`, `PUT|DELETE /dashboards/<id>`, `POST /widget-data`.

**Intel** `/api/intel`: `GET /types`, `GET /entities?type=&limit=`, `GET /entity?type=&value=`, `GET /filter-schema`, `GET /ip/<value>`, `POST /lookup` (enqueue enrichment), `POST /ingest` (connector-auth STIX bundle).

**Connectors** `/api/connectors`: `GET /status`, `GET /enrichers?entity_type=`, `GET /logs?tail=`.

**Settings** `/api/settings`: `GET|PUT /me` (per-user, stored in `users.settings`), `GET /global` (any user), `PUT /global` (admin; keys e.g. `graph.expand_warn_threshold`).

**Graph** `/api/graph`: `POST /seed` (`{seeds:[...]}`→`{nodes,edges,threshold}`), `POST /expansions` (`{ref,known_ids}`→one-hop options w/ counts), `POST /expand` (`{ref,key}`→one hop), `POST /links` (`{ref,known_ids}`→edges to existing nodes only).

**CORS admin** `/api/admin/cors` (admin): `GET|POST /origins`, `DELETE /origins/<id>`, `PATCH /origins/<id>/toggle`.

**TAXII feeds** `/api/taxii-feeds`: `GET`, `GET /<id>`, `POST`, plus update/delete.

**TAXII 2.1 server** `/taxii2` (api root `default`): `GET /`, `GET /default/`, `GET /default/collections/`, `GET /default/collections/<id>/`, `GET /default/collections/<id>/objects/`. Own `require_taxii_auth`.

**Misc**: `GET /` (info), `GET /health`, `GET /ofm.js`.

## Database schema (key)

- `sessions`: id, fsid, risk_score, flags(JSONB), client_ip, ip_observable_type/id, user_agent_observable_id, first/last_seen. Children: `fingerprints` (raw JSONB + `automation_*`, `device_*`, `browser_*`, `graphics_*`, `codecs_*`, `locale_*`, `det_*` [21 detection bools], `fast_bot_detection`, `url`), `heartbeats` (counts + `raw_behavior` JSONB), `behavioral_events` (session_id, event_type, url, data JSONB), `session_urls`, `browser_sessions`.
- `rules` (conditions JSONB, rule_type realtime|periodic, logic AND|OR, score_modifier, period_seconds) → `rule_matches`.
- `dashboards` (widgets JSONB). `users` (+`settings` JSONB per-user prefs), `api_tokens`, `allowed_origins`, `taxii_feeds`, `app_settings` (key PK, value JSONB — global settings e.g. `graph.expand_warn_threshold`).
- **STIX tables** (shared cols: id, stix_id[unique], value[indexed], created_at_platform, last_refreshed_at, decayed, raw JSONB): `stix_ipv4_addr`, `stix_ipv6_addr`, `stix_user_agent`, `stix_autonomous_system`, `stix_country`, `stix_indicator`, `stix_malware`, `stix_campaign`, `stix_intrusion_set`, `stix_relationship` (source_ref/target_ref cross-table STIX IDs). STIX IDs deterministic (UUIDv5) → dedup. `decayed` set once older than `INTEL_DECAY_DAYS`.

## Filters / schema

- Condition format: `{"field","op","value"}`. Field registry: `services/schema.py` `SCHEMA_FIELDS` (name, label, type, model, column). Fingerprint fields auto-generated from fpscanner `types.ts` (`signals.*`, `fastBotDetectionDetails.*`).
- Ops — string: `eq neq contains not_contains starts_with ends_with` (ILIKE); number: `eq neq gt gte lt lte`; boolean: `eq` ("true"/"false").
- Behavioral virtual fields (computed from `behavioral_events`): `behavior_button_click_count`, `behavior_form_submit_count`, `behavior_copy_count`, `behavior_paste_count`, `behavior_button_text`, `behavior_form_action`, `behavior_form_method`, `behavior_event_url`.
- Autocomplete `GET /api/suggest`: string→`DISTINCT ILIKE LIMIT 20`, boolean→`["true","false"]`, number→`[]`.

## Connectors (`connectors/`)

- Shared lib `connectors/base/connector_base/`: `load_config`, `ConnectorRunner`, `log_shipper`.
- `config.yml`: `name` (required, queue routing), `mode` (`manual|auto|both`), `connector_type` (`enricher|importer`), `scope` (STIX types), infra URLs; unknown keys → `config.params`. Env overrides: `RABBITMQ_URL`, `BACKEND_URL`, `CONNECTOR_TOKEN`.
- Handler receives `{request_id, type, value, connector}`, returns STIX 2.1 bundle dict.
- **ipinfo**: IPinfo Lite, scope ipv4/ipv6 → AS (`belongs-to`) + country (`located-at`).
- **opencti**: scope ipv4/ipv6/user-agent → indicators/malware/campaigns/intrusion-sets + relationships.

## Redis keys / RabbitMQ

- `ofm:events` (queue), `ofm:logs`, `ofm:connector:<name>:{heartbeat(TTL30s),mode,type,scope}`.
- Exchange `ofm.intel` → `intel.requests.<name>`; responses → `intel.responses`.

## Frontend (`frontend/src/`)

- `App.jsx` — BrowserRouter (no basename), `ProtectedRoute`/`AdminRoute`, `AuthContext`. `api.js` central client. `hooks/usePersistentState.js` — per-user localStorage state.
- Pages: `Dashboard/` (session table + drag-drop widgets + `FilterBuilder`, `WidgetWizard`; saved dashboards; middle-click row → new-tab `/session/:fsid`; checkbox multi-select → `Explore in graph`), `SessionDetail/`, `Intelligence/` (STIX browser; deep-link `/intelligence?type=&value=`; middle-click → new tab; `Explore in graph`), `Graph/` (Cytoscape.js graph explorer, see below), `Logging/` (connector health + logs + admin Graph threshold), `Login/`, `Landing/`, `Profile/` (password + API tokens), `Users/` (admin), `Rules/` (admin), `Exports/`.
- Components: `FilterBuilder`, `WidgetWizard`, `NavHeader`, `IpIntelPopover`.
- Widget types: stat, pie chart, histogram, weighted list — each with own filter conditions.

## Graph explorer (`frontend/src/pages/Graph/`, `backend/services/graph.py`)

Full docs: `docs/graph.md`. Route `/graph?seeds=<url-encoded JSON array>` (Cytoscape.js). Graph assembled on-demand from DB; layout + metadata edges never persisted.

- **Node kinds**: `session` (`session:<fsid>`, circle w/ red risk pie + centered score), `stix` (`stix:<stix_id>`, diamond; labeled by `raw.name` when present), `property` (`property:<field>:<value>`, rounded-rect; curated whitelist: platform, timezone, language, screen_resolution), `flag` (`flag:<flag>`, warning triangle). **Edge kinds**: `stix_relationship` (solid arrow, from `stix_relationship` rows), `metadata` (dashed, session↔stix/property/flag; visualization-only).
- **Seeds**: `{kind:"session",fsid}` | `{kind:"stix",type,value|stix_id}`. Launch from Dashboard checkbox multi-select, SessionDetail, Intelligence. Session seed also pulls its IP+UA observables. Helpers in `pages/Graph/graphLink.js` (`buildGraphUrl`, `parseSeeds`, `sessionSeed`, `stixSeed`).
- **Expansion = strictly one hop**. Options carry exact `count` of NEW nodes (deduped vs `known_ids`); `warn`/red badge + confirm when `count >= graph.expand_warn_threshold` (global, default 1000, admin-editable). No hard cap. Option `group ∈ {linked,relationships,sessions,property,flag}` (buttons vs searchable dropdowns for flag/property). Keys: session→`role:ip`,`role:user-agent`,`property:<field>`,`flag:<name>`; stix→`linked_sessions`,`reltype:<stix_type>` (per related type); property/flag→`sessions`.
- **Auto-link** (`compute_links`, user setting `graph.autoLink` default on): when a node is added (expand/add/seed), draws edges from it to already-present nodes so real relationships (e.g. AS→all its IPs on graph) appear even if the neighbour pre-existed. Returns edges only.
- **Bulk expand**: select 2+ same-kind (+same stixType) nodes → union of per-node expansions by `category`, apply chosen key to all. **Interactions**: wheel zoom (sensitivity 1), drag-bg pan, node drag, ctrl/⌘+click additive select + group drag, right-click context panel (metadata + expansions + Browse→session/intel new tab). Bottom bar: zoom/fit/layout/settings/delete/bulk/select-by-type/Add-entity. **Add-entity drawer**: search kind selector (Session|STIX type) + optional filters (session schema or intel filter-schema) + results with `+`.
- **Settings**: per-user `users.settings.graph` = `{colors:{session,property,flag,stix:{<type>}},riskRing:{enabled,color},autoLink}` via `GET|PUT /api/settings/me`, loaded by `hooks/useUserSettings.js`. Backend defaults `services/settings.py::USER_SETTINGS_DEFAULTS`; global `GLOBAL_DEFAULTS` (`graph.expand_warn_threshold`). `services/graph.py`: `PROPERTY_FIELDS`, `STIX_TYPE_LABELS`, `resolve_seeds`, `get_expansions`, `expand`, `compute_links`; endpoints in `routes/graph.py`.

## Client script (`client/src/`)

- `index.js` entry: runs fpscanner, `collect()` → `/api/initial`, registers extensions. `config.js` endpoints + `OFM_SERVER_URL` (build-time Vite inject; empty=same-origin). `send.js` beacon/fetch transport.
- Extensions (`extensions/`): `behavior.js` — buffers low-signal (mousemove/scroll/keys/touch, throttled), sends high-signal directly (button_click, form_submit, copy, paste). `drain()` flushed each heartbeat. `CFG.captureFormValues` gates form value capture. Debug hook `window.__OFM__`.

## Key env vars

`DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `JWT_SECRET`, `JWT_EXPIRY_HOURS`, `OFM_ADMIN_USERNAME/PASSWORD/TOKEN`, `INTEL_DECAY_DAYS`(7), `PERIODIC_INTERVAL_SECONDS`(60), `FPSCANNER_KEY` (must match fpscanner build key), `OFM_SERVER_URL`, `FLASK_DEBUG`, `LOG_LEVEL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`. License: MIT.
