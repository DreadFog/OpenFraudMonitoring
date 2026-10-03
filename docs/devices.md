# Device Identification

`Device` is a cluster of sessions believed to belong to the same physical
device, resolved via conservative hardware-group matching. It exists because
`Session.visit_id` identifies one browser-tab visit. `Session.fsid` is a
fingerprint value and may repeat across independent visits.

## Why not just use `fsid`?

FPScanner generates `fsid` by concatenating hashes of several signal
sections (device, browser, graphics, locale, ...). One of those sections
includes `graphics.canvas.canvasFingerprint`. On browsers that randomize
canvas output (privacy-hardened Firefox, some anti-fingerprinting
extensions, certain mobile browsers), that single volatile value changes
the whole `fsid` even though nothing about the underlying hardware changed.
`POST /api/initial` now finds visits by `visit_id`, not `fsid`; fingerprint
drift therefore does not merge or split visits.

`Device` decouples hardware correlation from visit ID and `fsid`:
`sessions.device_id` links each visit to a `Device` resolved by
comparing *stable* signals, not the full fingerprint.

## Required evidence groups

Unknown UUIDs merge only when all three groups match one coherent creation
profile. Missing values never reduce the requirements.

| Group | Required agreement |
|---|---|
| Graphics/model | An informative WebGL hardware renderer or specific UA-CH device model agrees. Any additional comparable informative renderer/model must also agree. |
| Display | Screen width, height, pixel depth and color depth are all positive, finite and equal. Together they count as one group. |
| Capacity | CPU logical-core count and device memory are both positive, finite and equal. Together they count as one group. |

Known hardware model patterns qualify GPU renderers; software renderers
(SwiftShader, llvmpipe, softpipe, lavapipe), generic labels and sentinels do
not. Renderer equality normalizes case and whitespace, not driver details.
UA-CH model identifiers must contain a model number. Unsupported identifiers
fail conservatively rather than accepting a generic vendor as identity.

Platform family and comparable UA-CH platform/architecture/bitness must not
contradict. Internally inconsistent ARM-platform/x86-architecture readings
also fail. Timezone, language, codecs, media counts, canvas, behavioral flags
and IP proximity cannot establish or rescue a hardware match.

Firefox display and capacity signals are considered uncertain on either
side: user-agent alone cannot prove RFP is disabled. Such readings cannot
fuzzy-merge unknown UUIDs, even when GPU/model agrees. Known UUIDs still work.

## Matching algorithm (`backend/services/device_matching.py`)

Resolution order on every `POST /api/initial`:

1. **Known UUID:** use its `DeviceCookie` association, preserving the
  association's original confidence. Hardware conflicts are logged but do
  not break UUID continuity or overwrite the creation profile. UUIDs are
  browser/profile/origin-local and client-supplied, not authentication.
2. **Unknown UUID or absent UUID:** first require a complete eligible incoming
  reading. Search all devices with matching display and capacity columns,
  without a recent-device limit or first-candidate tie breaker. These
  columns are only a prefilter; assess each immutable `match_profile`.
3. **Exactly one eligible candidate:** link with heuristic confidence `0.95`
  and persist the matched groups/conflicts with the new UUID association.
  This number is not a calibrated physical-device probability.
4. **Zero or multiple eligible candidates:** create a new device and freeze
  the incoming reading as its creation profile. Creation confidence `1.0`
  denotes a new identity, not proof of unique physical hardware.

Canonical hardware fields and `match_profile` retain the creation reading;
later requests cannot combine fields from different browsers into a synthetic
identity. IP history (last 20 addresses), last-seen, confidence and device-type
classification still update. Fuzzy matching is governed only by the evidence
group and unique-candidate requirements above.

### Existing deployments

Startup's additive column upgrades backfill an opaque UUID for every existing
session row, remove the unique constraint on `fsid`, and preserve existing
history. Old rows remain historical aggregates: their events cannot be split
into visits because no visit token was recorded. New requests use `visit_id`
exclusively. Existing devices have empty profiles and remain usable through
their existing UUIDs, but cannot receive new fuzzy associations.
Legacy aliases retain their historical confidence; its reliability is unknown.
No profile is automatically reconstructed from potentially contaminated
canonical fields, and no existing sessions or aliases are reassigned.
Repairing old clusters requires a separate backed-up, audited rebuild from
stored fingerprints. Deploy/restart both backend and worker with the new code
so their SQLAlchemy models and database schema remain consistent.

### v1.2 to v1.3 migration

The device rebuild and optional pruning procedure is maintained in the
[v1.2 to v1.3 migration helper guide](../migration_helpers/v1_2_to_v1_3/README.md).

## Data model

- `models/device.py` — `Device`: canonical Tier A/B fields, primary
  `cpu_count`, `memory`, immutable `match_profile` (JSONB), primary
  `cookie_id`, `device_bucket` (legacy summary), `recent_ips` (JSONB), `confidence`,
  `is_mobile`, `device_type`, `first_seen`/`last_seen`. `DeviceCookie`
  stores UUID aliases with `match_method` (`created`, `fuzzy`, or `legacy`),
  nullable `match_confidence`, `match_evidence` (JSONB), and first/last seen.
- `sessions.id` remains the internal row key; unique `sessions.visit_id`
  identifies a tab-scoped visit, while indexed `fsid` is non-unique fingerprint
  metadata.
- `sessions.device_id` — nullable FK to `devices.id`, added via the
  `_COLUMN_UPGRADES` additive-migration pattern in `services/database.py`
  (this repo has no migration framework).

Note: device type classification (mobile/workstation/unknown) is a
**device-level** field, not a session-level one — it's derived once per
fingerprint reading and stored on `Device`, not exposed on `Session` or the
session list API. It's only shown when browsing devices (`/devices`,
`/device/:id`), not on the session dashboard.

## API

- `GET /api/devices` — paginated list: id, platform, GPU renderer,
  device type, confidence, session/fsid/IP counts, first/last seen.
  Accepts `filters` (JSON array of `{field, op, value}`) and `logic` (`AND` default, or `OR`).
- `GET /api/devices/schema` — filterable device fields, generated from the
  `Device` model columns (see `services/device_filters.py`) plus linked-session
  aggregates: `sessions_count`, `distinct_fsids`, `distinct_ips`.
- `GET /api/devices/suggest?field=&q=` — autocomplete values for device string fields.
- `GET /api/devices/<id>` — full canonical field breakdown (incl. device
  type) + all linked sessions (fsid, risk score, IP, first/last seen).
- `GET|DELETE /api/sessions/<session_id>` — read or delete one visit using its
  internal numeric row ID. Session list/detail responses include `id`,
  `visit_id`, and fingerprint metadata `fsid`.
- `device_id` is also filterable from the existing session filter builder
  (`GET /api/schema`), since it's just another `Session` column.

## Frontend

- **Devices** page (`/devices`) — paginated device list with a confidence
  badge and device type per row, filterable with the same filter builder as
  the session view.
- **Device detail** (`/device/:id`) — canonical fields grouped by tier
  (including device type) + table of linked sessions (click-through to
  `/session/:session_id`).
  The hardware overview displays CPU core count and memory (GB); a Matching
  Profile section contains an expandable creation snapshot. Legacy devices
  show unknown hardware and "No snapshot".
- **Session detail** — a "View device" button links to the resolved
  device when `sessions.device_id` is set.
- **Dashboard** — session table groups by `device_id` ("Group by device"
  toggle) instead of by IP; it does not show device type, since that's
  device-level information (see above).

## Known limitations

- Independent machines with identical reported GPU/model, display and capacity
  can still collide. Fingerprinting establishes compatibility, not proof.
- Strict matching misses real correlations after hardware/display changes,
  with missing memory data, or with privacy-normalized Firefox readings.
- Existing contaminated aliases still resolve to their historical device
  until explicitly rebuilt; changing the matcher does not repair history.
- Driver-specific renderer changes can create separate devices for new UUIDs.
- Tracking devices/users across sessions via fingerprinting may have
  legal implications (e.g. GDPR) depending on your jurisdiction and use
  case, even when the stated purpose is fraud prevention.
