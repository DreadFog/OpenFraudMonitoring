# Device Identification

`Device` is a cluster of sessions believed to belong to the same physical
device, resolved via weighted fuzzy matching. It exists because
`Session.fsid` — while useful for exact-repeat forensics — is not a stable
long-term identity key.

## Why not just use `fsid`?

FPScanner generates `fsid` by concatenating hashes of several signal
sections (device, browser, graphics, locale, ...). One of those sections
includes `graphics.canvas.canvasFingerprint`. On browsers that randomize
canvas output (privacy-hardened Firefox, some anti-fingerprinting
extensions, certain mobile browsers), that single volatile value changes
the whole `fsid` even though nothing about the underlying hardware changed.
Since `sessions.fsid` is unique and used as the find-or-create key in
`POST /api/initial`, canvas drift alone used to create a brand-new
`Session` — breaking any attempt to track behavior for the same
device/user across days.

`Device` decouples long-term tracking from `fsid`: sessions keep their
`fsid` untouched (still useful for detecting exact repeats and forensics),
while `sessions.device_id` links each session to a `Device` resolved by
comparing *stable* signals, not the full fingerprint.

## Signal tiers

Only fields with a reasonable stability profile feed device identity.
Behavioral/automation signals (used by `analysis/risk.py`) are deliberately
excluded — a device shouldn't change identity because it started or stopped
looking automated.

| Tier | Fields | Stability | Weight |
|---|---|---|---|
| A — hardware | `device_platform`, screen width/height/pixel depth/color depth, multimedia device counts (speakers/mics/webcams), `graphics_web_gl_vendor`/`renderer`, UA-CH architecture/bitness/model | Changes almost never | 1–3 (see `_TIER_A_FIELDS` in `device_matching.py`) |
| B — OS/browser | UA-CH platform/platform version, timezone, language, audio/video codec hashes | Changes on OS/browser updates (weeks–months) | 1 (tie-breaker only) |
| Excluded | `graphics_canvas_canvas_fingerprint`, `graphics_webgpu_*`, `browser_maths`, `browser_etsl`, `browser_plugins_plugin_names_hash`, all `det_*`/`automation_*` | Volatile or behavioral, not identity | n/a |
| Conditionally excluded | Screen width/height, **only when the user agent is Firefox** | Firefox's Resist Fingerprinting (RFP) protection spoofs `screen.width`/`height` from the content viewport instead of real hardware, so the reported resolution can differ from the real display and drift with window size/zoom | n/a for Firefox readings |

## Matching algorithm (`backend/services/device_matching.py`)

Resolution order, on every `POST /api/initial`:

1. **Client device UUID** (`extensions.device_id.uuid`, generated once and
  persisted in `localStorage` by the `device_id` client extension) — if a
  `DeviceCookie` alias already has this `cookie_id`, link immediately at
  confidence `1.0`. This is the strongest signal since it survives
  fingerprint drift entirely, but it's browser/profile-local and easy for
  a user to clear.
2. **Bucket prefilter** — candidates are narrowed to `Device` rows sharing
   the same `device_bucket` (`"<platform>|<width>x<height>"`), so scoring
   doesn't have to scan every device in the table. If no candidates share
   the bucket at all (e.g. the same physical device seen through a
   different browser landing in a different bucket scheme — see the
   Firefox RFP case below), fall back to a bounded scan of the most
   recently active `Device` rows sharing the same `platform`
   (`FALLBACK_SCAN_LIMIT = 200`) before giving up.
3. **Weighted field-agreement score** — for each candidate, `score_match()`
  compares every Tier A/B field that is recorded on **both** the existing
  device and the incoming fingerprint. Missing browser-specific signals
  (e.g. Firefox omitting UA-CH/WebGL details) are excluded from scoring —
  absence of evidence is not treated as a mismatch. At least
  `MIN_MATCH_EVIDENCE_WEIGHT = 8` weighted points must be comparable before
  a score can be accepted. The score is `matched_weight / total_weight`, a
  value in `[0, 1]`.
4. **IP/subnet proximity boost** — if the incoming client IP (or its /24,
   for IPv4) appears in the candidate's `recent_ips`, add a small boost
   (`IP_PROXIMITY_BOOST = 0.05`, capped at 1.0). This can nudge a
   borderline match but can never single-handedly cause one.
5. The candidate with the highest score is accepted if it's ≥
   `DEVICE_MATCH_THRESHOLD` (config, default `0.75`, env
   `DEVICE_MATCH_THRESHOLD`). Otherwise a new `Device` is created.

### Firefox Resist Fingerprinting (RFP)

Firefox's [fingerprinting protection](https://support.mozilla.org/kb/firefox-protection-against-fingerprinting)
spoofs `screen.width`/`screen.height` based on the browser's content viewport
rather than the real display — e.g. a real 5120×1440 monitor was reported as
5717×1608 in testing. Since this value isn't tied to hardware, it can differ
session to session (window resize, zoom) even on the same device.

`device_matching.py` detects Firefox from `browser_user_agent` and, only for
those readings:

- excludes `screen_width`/`screen_height` from the weighted score (they're
  skipped entirely, not just down-weighted, same treatment as canvas),
- falls back to `"<platform>|firefox-rfp|<gpu renderer>"` for the bucket key
  instead of `"<platform>|<width>x<height>"`,
- does not overwrite the device's stored `screen_width`/`screen_height` with
  the untrustworthy value (most-recent-write-wins only applies to fields the
  current reading can be trusted for).

Since this still leaves the Firefox bucket key different from a non-Firefox
bucket for the same device, the platform-only fallback scan (step 2 above)
is what allows the two to still merge — as long as enough of the remaining
Tier A/B fields (platform, timezone, language, ...) agree above
`DEVICE_MATCH_THRESHOLD`.

On every resolution — match or create — the device's canonical fields are
refreshed most-recent-write-wins (only non-empty incoming values overwrite
stored ones), the client IP is appended to `recent_ips` (capped at 20,
deduplicated), the seen browser/profile UUID is stored as a `DeviceCookie`
alias, and `last_seen`/`confidence` are updated. `is_mobile`/`device_type`
(`mobile`/`workstation`/`unknown`) are also recomputed from the incoming
signals each time via `derive_device_type()`, but only applied when the
reading yields a confident classification — an ambiguous reading never
downgrades a device's classification back to `unknown`.

## Data model

- `models/device.py` — `Device`: canonical Tier A/B fields, primary
  `cookie_id`, `device_bucket`, `recent_ips` (JSONB), `confidence`,
  `is_mobile`, `device_type`, `first_seen`/`last_seen`. `DeviceCookie`
  stores all browser/profile UUID aliases linked to that device.
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
- `GET /api/devices/<id>` — full canonical field breakdown (incl. device
  type) + all linked sessions (fsid, risk score, IP, first/last seen).
- `device_id` is also filterable from the existing session filter builder
  (`GET /api/schema`), since it's just another `Session` column.

## Frontend

- **Devices** page (`/devices`) — paginated device list with a confidence
  badge and device type per row.
- **Device detail** (`/device/:id`) — canonical fields grouped by tier
  (including device type) + table of linked sessions (click-through to
  `/session/:fsid`).
- **Session detail** — a "View device" button links to the resolved
  device when `sessions.device_id` is set.
- **Dashboard** — session table groups by `device_id` ("Group by device"
  toggle) instead of by IP; it does not show device type, since that's
  device-level information (see above).

## Known limitations

- Matching weights and the `0.75` threshold are initial estimates, not
  empirically tuned — expect to adjust `DEVICE_MATCH_THRESHOLD` and the
  per-field weights in `device_matching.py` against real traffic.
- Two different browser profiles (or browsers) on the same physical
  machine can share enough Tier A signals to cluster into one `Device`.
  This is intentional — it's a useful fraud signal (same-hardware,
  multiple accounts) — but it means a `Device` should be read as
  "confidently the same hardware", not "confidently the same person".
- The platform-only fallback scan is bounded (`FALLBACK_SCAN_LIMIT = 200`,
  most-recently-active first) to keep cost predictable; on a platform
  with a very high device churn, an older matching device could fall
  outside that window and still end up duplicated.
- `recent_ips` has no time-based decay in this version; a very old IP
  still counts toward the proximity boost.
- Tracking devices/users across sessions via fingerprinting may have
  legal implications (e.g. GDPR) depending on your jurisdiction and use
  case, even when the stated purpose is fraud prevention.
