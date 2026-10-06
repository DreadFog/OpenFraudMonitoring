# OpenFraudMonitoring v1.3 to v1.4 STIX Migration

This migration normalizes supported `raw` STIX JSON objects to the v1.4
OpenCTI-compatible contract. Platform columns such as `created_at_platform`,
`last_refreshed_at`, `decayed`, and `source_connector_id` are not changed.
The operation does not alter the database schema.

It removes OFM-only keys from embedded STIX JSON, maps legacy user-agent
`string` to `value`, maps country markers to `x_opencti_*`, adds required SDO
and SRO version timestamps, and retains the local row's STIX ID. It does not
rewrite session references or IDs.

## Dry Run

Deploy the v1.4 backend and run the migration in dry-run mode first:

```bash
docker compose run --rm --no-deps -T \
  -v "$PWD/backend:/app:ro" -v "$PWD:/workspace:ro" \
  -e PYTHONPATH=/app:/workspace backend \
  python -m migration_helpers.v1_3_to_v1_4.migrate_stix
```

Review the number of rows requiring normalization and any reported invalid
objects. Invalid rows prevent applying the migration.

## Apply

Take a full PostgreSQL backup before applying. Stop the backend, worker, and
connectors so they cannot write STIX objects during the migration. The migration
requires a new JSON backup path and holds exclusive locks on the STIX tables.

```bash
docker exec ofm-db pg_dump -U ofm -Fc ofm > "$HOME/ofm-before-v1.4-stix.dump"
docker compose stop backend worker connector-ipinfo connector-opencti
docker compose run --rm --no-deps -T \
  -v "$PWD/backend:/app:ro" -v "$PWD:/workspace:ro" \
  -v "$HOME:/backup" -e PYTHONPATH=/app:/workspace backend \
  python -m migration_helpers.v1_3_to_v1_4.migrate_stix \
  --apply --backup /backup/ofm-v1.3-to-v1.4-stix.json
docker compose up -d backend worker connector-ipinfo connector-opencti
```

The JSON backup records each changed row's prior and resulting `raw` payload.
It is created exclusively with mode `0600`; it is not a substitute for the
database dump. A transaction failure rolls back all row updates.