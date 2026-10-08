# LLM.md — OpenFraudMonitoring

Dense technical reference for LLMs. Self-hosted browser fingerprinting, behavioral analysis, bot detection, and STIX threat-intel platform. One `<script src="/ofm.js">` tag collects fingerprints + behavior; a React dashboard visualizes and scores sessions.

## Stack

- **Backend**: Python 3.11, Flask 2.3, Flask-SQLAlchemy 3.1 / SQLAlchemy 2.0, Flask-Bcrypt, PyJWT, pika (RabbitMQ), redis-py, stix2 3.0.
- **DB**: PostgreSQL 16 (JSONB + denormalized columns). Schema created via `create_all()` — **no migration tool**; column additions require manual `ALTER TABLE` (see `_COLUMN_UPGRADES`) / DB recreate.
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

1. Browser loads `ofm.js` → sessionStorage creates/reuses a per-tab `visit_id`; fpscanner generates deterministic fingerprint `fsid` → encrypted payload + `visit_id` → `POST /api/initial`.
2. Backend decrypts (XOR+Base64, key=`FPSCANNER_KEY`), upserts `Session` by `visit_id` (`fsid` is non-unique fingerprint metadata), resolves the fuzzy-matched `Device` (`services/device_matching.py`, see `docs/devices.md`) and sets `session.device_id`, sets authentication/domain snapshots, stores the fingerprint and STIX observables, queues rule evaluation, and may trigger connectors.
3. Every 30s, heartbeat and high-signal behavioral events carry the same `visit_id` and attach to that tab's visit. No `fsid` or IP fallback is used. Credential redaction and form-submit value removal are unchanged. Existing rows remain historical aggregates because old events have no visit token and cannot be split reliably.
4. Worker: realtime loop `BRPOP ofm:events` evaluates enabled `realtime` rules on the triggering session; periodic loop (every `PERIODIC_INTERVAL_SECONDS`) evaluates `periodic` rules over all sessions. Matches create `RuleMatch`, append rule name to `session.flags`, add `score_modifier` (capped 100).
5. Connectors consume `intel.requests.<name>` (exchange `ofm.intel`), call external API, publish STIX bundle to `intel.responses`; worker `ingest_bundle()` persists per-type STIX tables.
6. Frontend polls `GET /api/sessions` (~10s) with `?filters=[...]`.

## Backend layout (`backend/`)

### STIX v2.1

- Models are grouped under `backend/models/stix/{sco,sdo,sro}/`; `models.stix` re-exports the model names for existing imports.
- Canonical STIX/OpenCTI JSON remains in `raw`, is returned as `stix_object`, and is the only STIX payload exported by TAXII. API navigation keys stay at wrapper level (`stix_type`, `stix_id`, indexed `value`); OFM lifecycle/provenance is nested under `platform`.
- User-agent records use the OpenCTI-compatible `value` and `x_opencti_*` shape; `user-agent` is not a STIX 2.1-defined SCO. Country records are `location` SDOs. Configured IPinfo/OpenCTI sources are treated as trusted enrichment sources; see `docs/stix.md`.
- Existing STIX payloads are normalized by `migration_helpers/v1_3_to_v1_4/migrate_stix.py` (dry-run by default; explicit JSON backup required to apply).

- `app.py` — Flask app, dynamic CORS via `after_request` (origins from DB), registers routes, seeds rules + admin.
- `worker.py` — 3 threads: realtime (main), periodic, intel-response consumer.
- `init/config.py` — `Config` from env. `init/generate_schema.py` + `_generated_schema.py` — schema autogen from fpscanner `types.ts`. `init/seed_users.py`, `init/seed_rules.py`.
- `models/`: `session.py` (Session + internal numeric `id` + unique per-tab `visit_id` + non-unique indexed `fsid` + STIX observable FKs + device/auth/domain metadata), `fingerprint.py` (`extract_fields()` denormalizes JSONB), `device.py` (conservative fuzzy-matched device cluster; see `docs/devices.md`), `heartbeat.py`, `behavioral_event.py`, `rule.py` (Rule + RuleMatch), `associations.py` (SessionURL, BrowserSession), `dashboard.py`, `user.py` (User + ApiToken; `settings` JSONB for per-user prefs), `app_setting.py` (AppSetting = global key/value), `cors.py` (AllowedOrigin), `domain.py` (DomainConfig — monitored domain, auth cookie name, login-form pattern), `taxii_feed.py` (TaxiiFeed), `stix/` (SCO, SDO, and SRO model subpackages; `models.stix` compatibility re-exports).
- `services/`: `database.py` (+`_apply_column_upgrades` adds session/user fields and device matching profiles/provenance — no migration tool), `auth.py` (hash/JWT/API-token/decorators), `device_matching.py` (`resolve_device` — UUID alias lookup preserves link confidence; unknown UUIDs require graphics/model + display + CPU/memory groups against exactly one immutable `match_profile`, no hardware contradictions; `assess_match` returns eligibility/groups/conflicts; no IP boost or generic-field fallback; Firefox readings are uncertain; legacy empty profiles cannot fuzzy-match), `domains.py` (`normalize_domain`, `domain_from_url`, `configured_domain_for_host`, `auth_cookie_present`, `add_session_domain`, `form_action_matches`, `matching_form_config`; DEBUG logs `auth cookie check` / `auth form check`), `event_queue.py` (Redis), `mq.py` (RabbitMQ publish/consume), `schema.py` (`SCHEMA_FIELDS` registry), `intel_ingest.py` (`ingest_bundle`), `stix_store.py` (get_or_create), `stix_filters.py`, `cors_origins.py` (`dynamic_origin`), `log_shipper.py` (ships WARNING+ to Redis `ofm:logs`), `settings.py` (user/global settings defaults+merge), `graph.py` (graph node/edge builders, expansions, `compute_links`), `device_filters.py` (`DEVICE_FIELDS` auto-generated from `Device.__table__.columns` + linked-session aggregates `sessions_count`/`distinct_fsids`/`distinct_ips` as correlated subqueries; `build_device_query`, `get_device_schema`, `suggest_device_values`).
- `rules/engine.py` — `build_condition`, `apply_operator(column, type, op, value)` (shared op→SQL mapping, reused by device filters), `build_session_query` (fingerprint conditions wrapped in `EXISTS`); `evaluate_rule`. `rules/defaults/*.json` auto-seeded.
- `analysis/risk.py` — base risk score from fpscanner `fastBotDetectionDetails` severity: high=+15, medium=+8, low=+3.
- `filters/` — behavior filter registry + IP filters + domain filters + autocomplete suggestions.

## Auth & RBAC (`services/auth.py`, `routes/auth.py`)

- Login → short-lived **JWT** (HS256, `JWT_SECRET`, `JWT_EXPIRY_HOURS`=24). `Authorization: Bearer <jwt>`.
- **API tokens** format `ofm_<32hex>`, stored SHA-256 hashed + 12-char prefix; sent as Bearer too. Self-service under `/api/auth/tokens`.
- Roles: `user | admin | connector` (connector accounts have null password; used for intel source tracking).
- Decorators: `@require_auth` (sets `g.current_user`), `@require_role(*roles)`.
- Admin bootstrap: `OFM_ADMIN_USERNAME`/`OFM_ADMIN_PASSWORD` seeded on startup. `OFM_ADMIN_TOKEN` = shared connector→backend token.

## API endpoints (prefix → route)

**Auth** `/api/auth`: `POST /login`, `GET /me`, `PUT /password`, `GET|POST /tokens`, `DELETE /tokens/<id>`, `GET|POST /users` (admin), `PUT|DELETE /users/<id>` (admin), `POST /users/<id>/tokens` (admin).

**Collection** `/api`: `POST /initial`, `POST /heartbeat`, `POST /behavioral_event`; public `GET /latency` returns empty, uncached `204` with `X-OFM-Latency-Probe: 1`, wildcard CORS, and no DB/Redis access.

**Sessions** `/api`: `GET /sessions?filters=[...]`, `GET|DELETE /sessions/<session_id>` using the internal numeric row ID. Responses include the non-unique fingerprint `fsid` and visit UUID. `GET /stats`.

**Overview** `/api/overview` (landing page): `GET ''` → `{current, previous}` 24h-window counts (active sessions by `last_seen`, high risk ≥60, bots via flag keywords, new devices by `first_seen`), `review` (top 8 high-risk sessions 24h), `rules` (per-rule match counts 24h vs previous 24h + 24 hourly buckets + `spike`), `setup` (has_sessions, active origins/domains, healthy connectors, enabled rules). `GET /search?q=` → sessions (fsid/IP prefix), devices (id/cookie prefix), STIX ip/UA/AS entities.

**Devices** `/api`: `GET /devices?page=&per_page=&filters=[...]&logic=AND|OR` (paginated, filterable list), `GET /devices/schema` (device filter fields), `GET /devices/suggest?field=&q=`, `GET /devices/<id>` (canonical fields + linked sessions). See `docs/devices.md`.

**Filters** `/api`: `GET /schema`, `GET /suggest?field=&q=`.

**Rules** `/api` (admin): `GET|POST /rules`, `PUT|DELETE /rules/<id>`, `GET /rules/sequence-schema` (per-event-type sequence step fields from `_SEQUENCE_FIELDS`, used by the rule builder). Create/update return `{error}` on validation failure (surfaced in UI).

**Dashboards** `/api`: `GET|POST /dashboards`, `PUT|DELETE /dashboards/<id>`, `POST /widget-data`.

**Intel** `/api/intel`: `GET /types`, `GET /entities?type=&limit=`, `GET /entity?type=&value=`, `GET /filter-schema`, `GET /ip/<value>`, `POST /lookup` (enqueue enrichment), `POST /ingest` (connector-auth STIX bundle).

**Connectors** `/api/connectors`: `GET /status`, `GET /enrichers?entity_type=`, `GET /logs?tail=`.

**Settings** `/api/settings`: `GET|PUT /me` (per-user, stored in `users.settings`), `GET /global` (any user), `PUT /global` (admin; keys e.g. `graph.expand_warn_threshold`).

**Graph** `/api/graph`: `POST /seed` (`{seeds:[...]}`→`{nodes,edges,threshold}`), `POST /expansions` (`{ref,known_ids}`→one-hop options w/ counts), `POST /expand` (`{ref,key}`→one hop), `POST /links` (`{ref,known_ids}`→edges to existing nodes only).

**CORS admin** `/api/admin/cors` (admin): `GET|POST /origins`, `DELETE /origins/<id>`, `PATCH /origins/<id>/toggle`.

**Monitored domains** `/api/admin/domains` (admin): `GET|POST ''`, `PUT|DELETE /<id>`, `GET /export` (JSON download), `POST /import` (upsert by domain). See `docs/domains.md`.

**TAXII feeds** `/api/taxii-feeds`: `GET`, `GET /<id>`, `POST`, plus update/delete.

**TAXII 2.1 server** `/taxii2` (api root `default`, read-only, TAXII 2.1 OS): discovery `GET /`, `GET /default/`, `GET /default/collections/`, `GET /default/collections/<id>/`, `GET .../manifest/`, `GET|POST(403) .../objects/`, `GET|DELETE(403) .../objects/<object_id>/`, `GET .../objects/<object_id>/versions/`, `GET /default/status/<id>/` (404). Responses use `application/taxii+json;version=2.1` and TAXII error resources. Auth is `require_taxii_auth`: Basic, Bearer token/JWT, or `access_token`. Feed `object_types`/`filters` scope each collection. Tests: `backend/tests/test_taxii.py`.

**Misc**: `GET /` (info), `GET /health`, `GET /ofm.js`.

## Database schema (key)

- `sessions`: internal numeric `id`, unique tab `visit_id` UUID, non-unique indexed `fsid` fingerprint, risk/flags/IP/auth/domain fields, STIX references, `device_id`. Existing session rows are backfilled with opaque visit UUIDs but remain historical aggregates. Child fingerprints, heartbeats, URLs and behavioral events retain their session FK; new ingestion resolves that FK by `visit_id` only.
- `domain_configs`: id, `domain` (unique, normalized host), `auth_cookie_name`, `form_action`, `form_method` (default `post`), `form_field_names` (JSONB array), `active`, created/updated_at. See `docs/domains.md`.
- `devices`: id, primary `cookie_id` (origin-local client UUID), `device_bucket` (legacy summary), creation-reading canonical fields (platform, screen dims, `cpu_count`, `memory`, GPU vendor/renderer, UA-CH arch/bitness/model, timezone, language, codec hashes), immutable `match_profile` JSONB, `recent_ips` (capped 20, not matching evidence), heuristic `confidence`, first/last_seen. `device_cookies`: UUID aliases with `match_method`, nullable `match_confidence`, `match_evidence` JSONB and first/last seen. New fuzzy aliases get 0.95, repeats preserve that confidence. Existing clusters/aliases are not repaired automatically; legacy empty profiles cannot gain fuzzy aliases. See `docs/devices.md`.
- **Typed behavioral event tables** (replaced legacy `behavioral_events` JSONB table, all carry `authenticated`): `beh_copy` (`CopyEvent`: length, text?, source_tag/id/name/type, form_action), `beh_paste` (`PasteEvent`: length, text?, target_tag/id/name/type, form_action), `beh_form_submit` (`FormSubmitEvent`: action, method, field_names JSONB array + GIN index), `beh_button_click` (`ButtonClickEvent`: x, y, tag, text), `beh_auth_attempt` (`AuthAttemptEvent`: domain_config_id FK, action, method, matched_field_names — **server-generated only**, posting `event_type=auth_attempt` returns 400).
- `rules` (conditions JSONB, rule_type realtime|periodic, logic AND|OR, score_modifier, period_seconds) → `rule_matches`.
- `dashboards` (widgets JSONB). `users` (+`settings` JSONB per-user prefs), `api_tokens`, `allowed_origins`, `domain_configs`, `taxii_feeds`, `app_settings` (key PK, value JSONB — global settings e.g. `graph.expand_warn_threshold`).
- **STIX tables** (shared cols: id, stix_id[unique], value[indexed], created_at_platform, last_refreshed_at, decayed, raw JSONB): `stix_ipv4_addr`, `stix_ipv6_addr`, `stix_user_agent`, `stix_autonomous_system`, `stix_country`, `stix_indicator`, `stix_malware`, `stix_campaign`, `stix_intrusion_set`, `stix_relationship` (source_ref/target_ref cross-table STIX IDs). STIX IDs deterministic (UUIDv5) → dedup. `decayed` set once older than `INTEL_DECAY_DAYS`.

## Filters / schema

- Condition format: `{"field","op","value"}`. Field registry: `services/schema.py` `SCHEMA_FIELDS` (name, label, type, model, column). Fingerprint fields auto-generated from fpscanner `types.ts` (`signals.*`, `fastBotDetectionDetails.*`).
- Ops — string: `eq neq contains not_contains starts_with ends_with` (ILIKE); number: `eq neq gt gte lt lte`; boolean: `eq` ("true"/"false").
- Behavioral custom fields (computed from typed event tables): counts — `behavior_button_click_count`, `behavior_form_submit_count`, `behavior_copy_count`, `behavior_paste_count`; content — `behavior_button_text`, `behavior_form_action`, `behavior_form_method`, `behavior_form_field_name` (array contains), `behavior_event_url`; DOM context — `behavior_paste_target_name`, `behavior_paste_target_id`, `behavior_copy_source_name`, `behavior_copy_source_id`.
- Session-metadata fields: `authenticated` (boolean, plain Session column) and `domains` (custom filter in `filters/domain_filters.py` — JSONB array containment; ops `eq`/`contains`/`neq`/`not_contains`, autocomplete + widget aggregation).
- Sequence conditions (periodic rules only): `{"type":"sequence","steps":[{"event_type":"paste","filters":[...]},{"event_type":"form_submit","filters":[...]}]}` — Python-side greedy ordered scan. See `docs/rules.md` for full syntax and field reference.
- Autocomplete `GET /api/suggest`: string→`DISTINCT ILIKE LIMIT 20`, boolean→`["true","false"]`, number→`[]`.
- Device filters are a separate schema (`services/device_filters.py`): every `Device` column of type string/number/boolean (first/last_seen as date; JSONB/DateTime skipped) + aggregates; new Device columns appear automatically.

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
- Pages: `Dashboard/` (session table + drag-drop widgets + `FilterBuilder`, `WidgetWizard`; saved dashboards; middle-click row → new-tab `/session/:sessionId`; checkbox multi-select → `Explore in graph`), `SessionDetail/` (visit detail uses the numeric `sessionId`, links to `/device/:id` when `device_id` is set; overview shows `Authenticated` + `Domains`; activity timeline groups consecutive fully-authenticated URL-boxes into a green-bordered `🔒 Authenticated` cluster — heartbeat aggregation also splits on auth-state change — with a legend shown only when a group exists; timeline renders 🔐 auth attempts; multi-day sessions split URL-boxes at local-day boundaries and show dashed date dividers), `Devices/` (paginated device list with `FilterBuilder` over the device schema, filters persisted as `devices.filters`, `/devices`), `DeviceDetail/` (canonical fields + linked visits, `/device/:id`), `Intelligence/` (STIX browser; deep-link `/intelligence?type=&value=`; middle-click → new tab; `Explore in graph`), `Graph/` (Cytoscape.js graph explorer, see below), `Logging/` (Administration page, routes `/admin` + `/admin/:section`; sections in `Logging/adminSections.js`: `logging` (default — queues, connectors, recent logs with sticky UTC day dividers; polling only here), `monitoring` (CORS + monitored domains), `frontend` (dashboard global settings + privacy), `graph` (graph global settings), `users`; non-admins limited to `logging`; in-page tab bar + hover dropdown on the NavHeader "Administration" tab), `Login/`, `Landing/` (triage home at `/`, with the global NavHeader (hidden only on `/login`): quick search, 24h stat cards with deltas (click → Dashboard/Devices with preset filters via router `state: {filters, timeRange}`), Needs review, Rule activity sparklines (click → `triggered_flag` filter), admin Platform health, Recently viewed (`hooks/useRecentItems.js`, per-user localStorage `recent.items`, recorded by SessionDetail/DeviceDetail/Intelligence/Graph); first-run setup checklist replaces the triage view until the first session arrives, then shows compact for admins until hidden), `Profile/` (password + API tokens), `Users/` (admin, rendered in the `users` admin section), `Rules/` (admin; visual rule builder — plain conditions via `FilterBuilder` over `/api/schema`, plus a sequence editor for periodic rules over `/api/rules/sequence-schema`; enforces periodic+AND for sequences; JSON import/export kept), `Exports/`.
- Session UI/navigation uses numeric session row IDs (`/session/:sessionId`); `fsid` remains visible fingerprint metadata and may repeat across visits.
- Components: `FilterBuilder` (props `title`, `addLabel`, `className`, `suggest` — defaults to `api.getSuggestions`, `null` disables; buttons are `type="button"` so it is safe inside forms), `WidgetWizard`, `NavHeader`, `IpIntelPopover`, `CorsSettings`, `DomainSettings` (monitored-domain CRUD + JSON file import / export download).
- Widget types: stat, pie chart, histogram, weighted list — each with own filter conditions.
- Device overview (`/device/:id`) displays the new `cpu_count` and `memory` (GB) under Hardware, plus expandable `match_profile` in Matching Profile; legacy fields show unknown / No snapshot. The detail API returns these fields; the device list remains unchanged.

## Latency fingerprinting groundwork

- Numeric filter `latency_ms` (Session Metadata, label `Session Latency (ms)`) reads the latest `Session.latency.round_trip_ms` via a hybrid JSON-to-float SQL expression. Supports eq/neq/gt/gte/lt/lte in session filters, rules, and widgets; missing samples are SQL NULL, not zero. No extra column migration. PostgreSQL filter regression test uses disposable `LATENCY_TEST_DATABASE_URL`.
- Administration `/admin/server` (`ServerSettings`) configures `server.location` (`{name,latitude,longitude}`; optional paired coordinates) and `server.timezone` (IANA name, default UTC) through global settings. This does not change the host OS timezone.
- `client/src/extensions/latency.js` measures dedicated `CFG.latencyEndpoint` (`/api/latency`) with two sequential GETs per refresh: discarded warm-up then timed response headers. Fetch omits credentials, uses no-store, checks 204 + marker, and times out after 5s per request. Concurrent calls share a pair. Initial extension collection awaits probing; heartbeat drain starts background probing and returns the prior sample. Hidden pages skip probes; becoming hidden during timing discards that sample. `send.js` only attaches `latency.snapshot()`; ingestion duration never replaces it. Collection still uses credentialed fetch (15s timeout) or hidden-page beacon/fetch fallback. Proxy matchers must include `/api/latency`.
- Sample keys: `round_trip_ms`, `measured_at` (client epoch ms), `request_path` (no query), `measurement=lightweight_probe`, `client_timezone`, `client_utc_offset_minutes` (positive east). `services/latency.py` validates untrusted samples and attaches trusted server context at receipt, `received_at`, `source=client_reported`. Legacy ingestion samples remain `measurement=fetch_response_headers`; historical data is not rewritten. Public probe CORS bypass is in `services/cors_origins.py::apply_cors_headers`, registered by `app.py`; other routes keep DB-validated CORS.
- Latest sample in nullable JSONB `Session.latency` (detail API); per-heartbeat sample in `Heartbeat.latency` (summary API); normalized initial extension in fingerprint `_extensions.latency`; behavior events refresh session sample. `_COLUMN_UPGRADES` adds both JSONB columns for existing DBs. Retention deletes samples with their sessions/heartbeats.
- No matching connector, timezone mismatch detection, or risk scoring is implemented. Round trip includes network and server work and is not proof of location. Tests: `client/test/latency.test.cjs` via `npm test`; `backend/tests/test_latency.py` via unittest.

## Data retention

- Global setting `data.retention_months` defaults to 6 positive whole calendar months; admin control at `/admin/retention` (`RetentionSettings`).
- `services/retention.py::purge_inactive_data` runs on worker startup and hourly. Sessions expire by `last_seen` in milliseconds, strictly before the UTC calendar-month cutoff (month-end clamped).
- ORM session deletion cascades to fingerprints, heartbeats, URLs, browser sessions, rule matches, and all five typed behavioral-event tables. Use `db.session.delete(session)`, not bulk session deletion, to preserve these cascades.
- Devices with no retained visits and their cookie aliases are deleted. Surviving devices get session-derived `last_seen` and recent IP lists. Shared STIX observables/enrichment remain while retained visits need them; enrichment traversal does not cross into unrelated IP/UA leaves. Exclusive expired-visit entities and their relationships are removed; standalone intelligence expires by refresh/creation date.
- PostgreSQL advisory transaction lock prevents overlapping worker sweeps; failures roll back the sweep. Integration tests in `backend/tests/test_retention.py` require `RETENTION_TEST_DATABASE_URL` pointing only to a disposable PostgreSQL database (tests drop its schema).

## Graph explorer (`frontend/src/pages/Graph/`, `backend/services/graph.py`)

Full docs: `docs/graph.md`. Route `/graph?seeds=<url-encoded JSON array>` (Cytoscape.js). Graph assembled on-demand from DB; layout + metadata edges never persisted.

- **Node kinds**: `session` (`session:<session_id>`, circle w/ red risk pie + centered score), `stix` (`stix:<stix_id>`, diamond; labeled by `raw.name` when present), `property` (`property:<field>:<value>`, rounded-rect; curated whitelist: platform, timezone, language, screen_resolution), `flag` (`flag:<flag>`, warning triangle). **Edge kinds**: `stix_relationship` (solid arrow, from `stix_relationship` rows), `metadata` (dashed, session↔stix/property/flag; visualization-only).
- **Seeds**: `{kind:"session",id}` | `{kind:"stix",type,value|stix_id}`. Session IDs are internal numeric visit-row IDs; `fsid` is display/search fingerprint metadata. Launch from Dashboard checkbox multi-select, SessionDetail, Intelligence. Session seed also pulls its IP+UA observables. Helpers in `pages/Graph/graphLink.js` (`buildGraphUrl`, `parseSeeds`, `sessionSeed`, `stixSeed`).
- **Expansion = strictly one hop**. Options carry exact `count` of NEW nodes (deduped vs `known_ids`); `warn`/red badge + confirm when `count >= graph.expand_warn_threshold` (global, default 1000, admin-editable). No hard cap. Option `group ∈ {linked,relationships,sessions,property,flag}` (buttons vs searchable dropdowns for flag/property). Keys: session→`role:ip`,`role:user-agent`,`property:<field>`,`flag:<name>`; stix→`linked_sessions`,`reltype:<stix_type>` (per related type); property/flag→`sessions`.
- **Auto-link** (`compute_links`, user setting `graph.autoLink` default on): when a node is added (expand/add/seed), draws edges from it to already-present nodes so real relationships (e.g. AS→all its IPs on graph) appear even if the neighbour pre-existed. Returns edges only.
- **Bulk expand**: select 2+ same-kind (+same stixType) nodes → union of per-node expansions by `category`, apply chosen key to all. **Interactions**: wheel zoom (sensitivity 1), drag-bg pan, node drag, ctrl/⌘+click additive select + group drag, right-click context panel (metadata + expansions + Browse→session/intel new tab). Bottom bar: zoom/fit/layout/settings/delete/bulk/select-by-type/Add-entity. **Add-entity drawer**: search kind selector (Session|Device|STIX type) + optional filters (session schema, device schema with AND/OR, or intel filter-schema) + results with `+`.
- **Settings**: per-user `users.settings.graph` = `{colors:{session,property,flag,stix:{<type>}},riskRing:{enabled,color},autoLink}` via `GET|PUT /api/settings/me`, loaded by `hooks/useUserSettings.js`. Backend defaults `services/settings.py::USER_SETTINGS_DEFAULTS`; global `GLOBAL_DEFAULTS` (`graph.expand_warn_threshold`). `services/graph.py`: `PROPERTY_FIELDS`, `STIX_TYPE_LABELS`, `resolve_seeds`, `get_expansions`, `expand`, `compute_links`; endpoints in `routes/graph.py`.

## Client script (`client/src/`)

- `index.js` entry: runs fpscanner, `collect()` → `/api/initial`, registers extensions. `config.js` endpoints + `OFM_SERVER_URL` (build-time Vite inject; empty=same-origin). `send.js` beacon/fetch transport (fetch fallback uses `credentials: "include"`).
- **Cookie-based auth detection requires same-origin collection**: serve `/ofm.js` and proxy `/api/initial`, `/api/heartbeat`, `/api/behavioral_event` through each monitored host (`OFM_SERVER_URL=`). A separate OFM hostname never receives the monitored site's cookies. See `docs/deployment.md`.
- `extensions/privacy_notice.js` displays an informational fraud-monitoring banner with a GitHub link and **OK** dismissal, isolated in a shadow root. Host-scoped `ofm_notice_acknowledged=1` cookie remembers dismissal for one year (`Path=/; SameSite=Lax`, `Secure` on HTTPS). Collection does not wait for acknowledgment; this is not a consent gate. Cookie failures leave dismissal usable for the current page.
- Extensions (`extensions/`): `behavior.js` — buffers low-signal (mousemove/scroll/keys/touch, throttled), sends high-signal directly (button_click, form_submit, copy, paste). `drain()` flushed each heartbeat. `CFG.captureFormValues` gates form value capture. Debug hook `window.__OFM__`.

## Key env vars

`DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `JWT_SECRET`, `JWT_EXPIRY_HOURS`, `OFM_ADMIN_USERNAME/PASSWORD/TOKEN`, `INTEL_DECAY_DAYS`(7), `PERIODIC_INTERVAL_SECONDS`(60), `FPSCANNER_KEY` (must match fpscanner build key; passed to backend+frontend build args and backend runtime), `OFM_SERVER_URL`, `OFM_ENV`(production), `FLASK_DEBUG`, `LOG_LEVEL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`. License: AGPL-3.0 (see `LICENSE` + `NOTICE`; vendored `fpscanner/` stays MIT © 2017 antoinevastel).
