# STIX Object Contract

OFM stores the canonical STIX/OpenCTI JSON payload in each object's `raw`
column. The REST API returns this under `stix_object`; OFM-only state is under
`platform`. Existing top-level REST wrapper fields remain as compatibility
aliases, including `raw`; new clients should use `stix_object` and `platform`.
TAXII exports only `stix_object`, never the ORM wrapper.

The current model package is grouped by STIX category under
`backend/models/stix/`: `sco/`, `sdo/`, and `sro/`. `StixCountry` is a storage
model for a `location` SDO. Local table IDs, indexed `value`, platform arrival
and refresh times, decay state, and connector attribution remain platform data.
They are not embedded in the STIX JSON. The indexed `value` is retained as an
OFM search/navigation key; the canonical STIX fields remain in `stix_object`.

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

## Migration

Existing payloads are normalized by
`migration_helpers/v1_3_to_v1_4/migrate_stix.py`. Run it in dry-run mode and
review the required backup/apply procedure in
`migration_helpers/v1_3_to_v1_4/README.md` before applying it to production.