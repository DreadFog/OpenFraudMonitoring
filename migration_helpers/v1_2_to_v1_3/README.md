# OpenFraudMonitoring v1.2 to v1.3 Migration

This helper rebuilds device clusters using the v1.3 conservative matcher and
can prune historical sessions whose fingerprints resolve to multiple devices.
It is intentionally separate from application startup and defaults to a
read-only dry-run.

## What It Changes

The rebuild replays stored fingerprints chronologically, recreates devices and
UUID aliases, and updates `sessions.device_id`. Device IDs will change. If
`--prune-ambiguous` is enabled, it also deletes each ambiguous session and its
fingerprints, heartbeats, behavioral events, session URLs, browser-session rows,
and rule matches. It does not delete rules, STIX data, or the database schema.

Pruning is permanent unless restored from the full database dump. The JSON
backup contains old device/alias rows, session assignments, and pruned session
metadata/counts; it is not a substitute for a PostgreSQL dump.

## Dry Run

First deploy the v1.3 backend/worker/frontend so the additive schema upgrade has
run and the collector sends `visit_id`. Then preview the complete plan:

```bash
docker compose up -d --build backend worker frontend
docker compose run --rm --no-deps -T \
  -v "$PWD/backend:/app:ro" -v "$PWD:/workspace:ro" \
  -e PYTHONPATH=/app:/workspace backend \
  python -m migration_helpers.v1_2_to_v1_3.rebuild_devices
```

To preview pruning, add `--prune-ambiguous`:

```bash
docker compose run --rm --no-deps -T \
  -v "$PWD/backend:/app:ro" -v "$PWD:/workspace:ro" \
  -e PYTHONPATH=/app:/workspace backend \
  python -m migration_helpers.v1_2_to_v1_3.rebuild_devices --prune-ambiguous
```

Review the proposed device count, pruned session IDs, per-table child counts,
and `sessions_spanning_multiple_devices`. Cluster numbers in the report are
zero-based plan indexes, not database IDs. Do not apply if any ambiguous
sessions remain after pruning.

## Apply

Confirm the preview, schedule a maintenance window, and take a full database
backup. This example stores both backups under `$HOME/ofm-backups` and refuses to
overwrite either file:

```bash
mkdir -p "$HOME/ofm-backups"
docker exec ofm-db pg_dump -U ofm -Fc ofm > "$HOME/ofm-backups/ofm-before-v1.3-device-rebuild.dump"
docker compose stop frontend backend worker
docker compose run --rm --no-deps -T \
  -v "$PWD/backend:/app:ro" -v "$PWD:/workspace:ro" \
  -v "$HOME/ofm-backups:/backup" -e PYTHONPATH=/app:/workspace backend \
  python -m migration_helpers.v1_2_to_v1_3.rebuild_devices \
  --apply --prune-ambiguous \
  --backup /backup/devices-v1.2-to-v1.3.json
docker compose up -d frontend backend worker
```

`--apply` takes exclusive locks on session/device tables and performs pruning,
device replacement, alias creation, and session relinking in one transaction.
The JSON backup is created with mode `0600` and never overwrites an existing
path. A database error rolls back the transaction. If apply fails, inspect the
error and restore services only after verifying the database state.

Without `--prune-ambiguous`, apply refuses to proceed when any session spans
multiple planned devices. Sessions without fingerprints remain unlinked.
Historical behavioral records are deleted only for sessions explicitly listed
as ambiguous in the reviewed prune plan.