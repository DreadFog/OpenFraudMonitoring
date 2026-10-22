# STIX Object Contract

OFM stores the canonical STIX/OpenCTI JSON payload in each object's `raw`
column. The REST API returns this under `stix_object`; OFM-only state is under
`platform`. Existing top-level REST wrapper fields remain as compatibility
aliases, including `raw`; new clients should use `stix_object` and `platform`.
TAXII exports only `stix_object`, never the ORM wrapper.

The current model package is grouped by STIX category under
`backend/models/stix/`: `sco/`, `sdo/`, and `sro/`. `StixCountry` is a storage
model for a `location` SDO. Local table IDs, indexed `value`, platform arrival
and refresh times, indicator-only revocation state, and connector attribution remain platform data.
They are not embedded in the STIX JSON. The indexed `value` is retained as an
OFM search/navigation key; the canonical STIX fields remain in `stix_object`.

**Revocation is indicator-only in OFM.** Only indicators store or expose the
`revoked` property and offer it as an export/filter field. All other entities,
including malware, campaigns, countries, observables, and relationships, discard
this property during ingestion and editing. This is an OFM-specific restriction:
STIX itself allows revocation on other versioned objects too.

Backend startup removes legacy `revoked` keys from non-indicator `raw` JSON in
the database, preserving other fields and all indicator revocation state. The
cleanup is idempotent and runs under the existing schema-upgrade lock. Redeploy
backend, worker, and connectors together so older processes cannot reintroduce
the property. Existing generated CSV snapshots refresh on their next scheduled
generation.

## OpenCTI Compatibility

IPv4/IPv6 addresses and autonomous systems use their STIX 2.1 SCO property
names. Country records use `type: location`, standard Location SDO fields, and
OpenCTI extension properties such as `x_opencti_id`, `x_opencti_type`,
`x_opencti_location_type`, and `x_opencti_aliases`. User agents use the
OpenCTI-compatible `user-agent` object shape with `value` and `x_opencti_*`
properties; `user-agent` is an OpenCTI extension type, not a STIX 2.1-defined
SCO. The deprecated OFM `x_ofm_*` markers and the nonstandard `string` alias
are removed from canonical payloads.

Versioned SDO and SRO objects have STIX `created` and `modified` timestamps.
SCO objects do not acquire those timestamps. Relationship objects use the
standard `relationship` type and the standard relationship names used by OFM
enrichment (`based-on`, `belongs-to`, `located-at`, and `indicates`).
New SCO IDs use the OASIS deterministic-ID namespace; OFM-generated Location and
Relationship IDs use a separate namespace so it is not reused for SDOs/SROs.

## Source Trust

Configured IPinfo and OpenCTI connectors are treated as trusted enrichment
sources for ingestion. Connector provenance is recorded in the platform-only
`source_connector_id`; it is not substituted for STIX `created_by_ref`, which
identifies a STIX Identity object. For versioned objects that arrive without an
explicit STIX confidence, OFM uses `confidence: 100` under this source-trust
policy. This describes OFM's trust in the configured source, not independent
verification of the reported fact. SCOs use OpenCTI's `x_opencti_score` field
instead of the SDO/SRO confidence property.

## API Navigation

Responses retain `stix_type`, `stix_id`, and the indexed display/search `value`
at the entity wrapper level so frontend deep links remain stable. The
serialized object is under `stix_object`; platform timestamps and state are
under `platform`. Frontend object labels and detail panels should read STIX
properties from `stix_object` and OFM lifecycle state from `platform`.

Intelligence details summarize direct SCO-to-AS/location relationships in
their own context boxes and show unrevoked Indicators based on the SCO in a
separate known-behavior panel. Those summarized edges are omitted from the
generic relationship list. Indicator details separately show `valid_from`,
`valid_until`, the objects it indicates, and session count/first-seen/last-seen
statistics for the SCOs referenced by its `based-on` relationships. The labels
make clear that these session statistics belong to the underlying observable(s),
not to the Indicator itself.

## Local IP Indicators

Administrators can use **Create indicator** on IPv4/IPv6 rows and detail pages
in Intelligence. The action asks for confirmation because these indicators may
feed a firewall. It creates a STIX Indicator named with the IP address, an
equality pattern such as `[ipv4-addr:value = '192.0.2.1']`, and an outgoing
`based-on` relationship to the observable. User-agent and other entity types
do not offer this action.

If indicators are already related by `based-on`, the action renews all of them
instead of duplicating them. This includes imported/connector indicators and
explicitly revoked indicators: renewal clears revocation, updates `modified`
and platform refresh time, and extends `valid_until` without shortening a
longer existing validity. Imported names, patterns, IDs, other properties, and
connector attribution are preserved. Consequently an imported name is not
guaranteed to be an IP address and may not suit a name-only firewall feed.
Subsequent connector enrichment can overwrite these local lifecycle changes.

**Administration > Data management > IP Indicator Automation** controls the
global `intel.indicator_automation` policy:

| Field | Default | Accepted values |
| --- | --- | --- |
| `enabled` | `true` | Boolean |
| `risk_threshold` | `100` | Integer 0-100, inclusive |
| `lookback_minutes` | `60` | Integer 1-10080 |
| `validity_hours` | `24` | Integer 1-8760 |

Each periodic worker pass runs automation after rule scoring, including when no
periodic rules are configured. It groups recent qualifying sessions by linked
IPv4/IPv6 observable and uses the latest qualifying `last_seen` (milliseconds).
The rolling window also applies on worker restart; it does not scan all history.
Future-dated sessions are excluded. Settings are reloaded on every pass.

For example, with 24-hour validity, qualifying activity at 19:00 keeps the
indicator valid until at least 19:00 the following day; new activity at 20:00
extends that to 20:00 the following day. Repeated checks of unchanged sessions
do not accumulate days or keep inactive addresses valid forever. Manual renewal
uses the current time and the same duration, regardless of whether automation
is enabled. An expired candidate is not reactivated from old activity.

Indicators with `valid_until` expire at that instant. Indicators without it
retain the configured enrichment-inactivity revocation policy. Effective
revocation is recalculated for intelligence and CSV/TAXII reads, not just on the
hourly worker sweep. Explicit source revocation remains effective unless an
administrator or qualifying automatic activity renews the indicator.

**Automation is enabled by default**, and can reactivate previously revoked
indicators, but only from qualifying activity newer than the revocation (the
indicator's `modified` time when `revoked` is true). Activity that happened
before the revocation is ignored, so a revoke is not undone by the next pass;
**Create indicator** always reactivates. Review this policy before deploying
when exports drive enforcement.
For a [firewall feed](dissemination/README.md), export Indicator `name`, turn off
incremental batches, and filter on **Revoked = false** plus any desired scope.
The exporter does not automatically exclude revoked indicators; without that
filter, expired addresses remain in a full snapshot.

Manual API (admin only):

```http
POST /api/intel/indicators
Content-Type: application/json

{"type":"ipv4-addr","stix_id":"ipv4-addr--<uuid>"}
```

Returns `201` with `created: true` for a new indicator or `200` with
`created: false` for renewal, and an `indicators` array of serialized objects.
Policy updates use the existing admin-only `PUT /api/settings/global` endpoint
with the complete `intel.indicator_automation` object.

### Revoking and editing entities

Administrators can click **Revoke** on Indicator rows and detail pages. It sets
STIX `revoked: true` and sets both `valid_until` and `modified` to the revocation
time (millisecond precision). A `valid_from` at or after that time is moved 1 ms
earlier, keeping `valid_until` later than `valid_from` as STIX requires. The
indicator leaves feeds filtered on **Revoked = false**. Revoking an already
revoked and expired indicator changes nothing:

```http
POST /api/intel/indicators/<indicator stix_id>/revoke
```

Every entity detail page also has **Edit**, which opens a modal dialog with
labeled inputs, checkboxes for booleans, and grouped fields for nested properties
and lists. The entity ID is hidden and preserved, and platform-managed properties
and observable lookup values are read-only. Date/time pickers use UTC;
clearing **Valid until** removes the explicit expiry. Saving replaces
the object after normalization and validation:

```http
PUT /api/intel/entities/<stix_id>
Content-Type: application/json

{"stix_object": {...complete STIX object...}}
```

`type`, `id`, and `created` cannot change; `modified` is set to the edit time.
Observable lookup values (IP, user agent, AS number, country) are immutable, as
sessions and enrichment reference them. Indicators require valid ISO 8601
`valid_from`/`valid_until` (with `valid_until` later), a boolean `revoked`, and
recompute effective revocation immediately. Set `revoked` to `false` to
reactivate an indicator. A past `valid_until` keeps it expired. Edits do not change
platform refresh time or connector attribution. Later connector enrichment of
the same STIX ID can overwrite manual edits.

Rebuild/redeploy backend, worker, and frontend together. No schema migration is
required; policy uses existing settings storage and validity uses STIX JSON.
Generation and export integration tests run against PostgreSQL with
`INDICATOR_TEST_DATABASE_URL` pointing to a disposable test database:

```sh
cd backend
INDICATOR_TEST_DATABASE_URL=postgresql://localhost/ofm_test \
    python -m unittest discover -s tests -p test_indicator_generation.py -v
```

The tests create and remove their own isolated schema.

## Migration

Existing payloads are normalized by
`migration_helpers/v1_3_to_v1_4/migrate_stix.py`. Run it in dry-run mode and
review the required backup/apply procedure in
`migration_helpers/v1_3_to_v1_4/README.md` before applying it to production.