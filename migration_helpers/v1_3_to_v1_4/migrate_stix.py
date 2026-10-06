"""Normalize stored STIX payloads for the v1.4 OpenCTI-compatible contract."""

import argparse
import json
import os
import re
from datetime import datetime, timezone

from flask import Flask
from sqlalchemy import text

import models
from init.config import Config
from services.database import db
from services.stix_objects import normalize_stix_object


MODEL_TYPES = (
    (models.StixIPv4Addr, "ipv4-addr"),
    (models.StixIPv6Addr, "ipv6-addr"),
    (models.StixUserAgent, "user-agent"),
    (models.StixAutonomousSystem, "autonomous-system"),
    (models.StixCountry, "location"),
    (models.StixIndicator, "indicator"),
    (models.StixMalware, "malware"),
    (models.StixCampaign, "campaign"),
    (models.StixIntrusionSet, "intrusion-set"),
)


def _legacy_object(row, stix_type):
    obj = dict(row.raw or {})
    obj.setdefault("type", stix_type)
    obj.setdefault("id", row.stix_id)
    if stix_type in {"ipv4-addr", "ipv6-addr", "user-agent"}:
        obj.setdefault("value", row.value)
    elif stix_type == "autonomous-system":
        digits = re.sub(r"\D", "", str(row.value))
        obj.setdefault("number", int(digits) if digits else None)
        obj.setdefault("name", row.value)
    elif stix_type == "location":
        obj.setdefault("name", row.value)
        obj.setdefault("country", row.value)
        obj.setdefault("x_ofm_location_type", "Country")
    elif stix_type == "indicator":
        obj.setdefault("pattern", row.value)
    elif stix_type in {"malware", "campaign", "intrusion-set"}:
        obj.setdefault("name", row.value)
    return obj


def _timestamp_text(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _changes():
    changes = []
    errors = []
    for model, stix_type in MODEL_TYPES:
        for row in model.query.order_by(model.id).all():
            old_raw = row.raw or {}
            try:
                normalized = normalize_stix_object(
                    _legacy_object(row, stix_type),
                    platform_created_at=row.created_at_platform,
                )
            except (TypeError, ValueError) as exc:
                errors.append(f"{model.__tablename__}:{row.id} ({row.stix_id}): {exc}")
                continue
            if normalized != old_raw:
                changes.append({
                    "table": model.__tablename__,
                    "row_id": row.id,
                    "stix_id": row.stix_id,
                    "old_raw": old_raw,
                    "new_raw": normalized,
                    "row": row,
                })

    for row in models.StixRelationship.query.order_by(models.StixRelationship.id).all():
        old_raw = row.raw or {}
        obj = dict(old_raw)
        obj.update({
            "type": "relationship",
            "id": row.stix_id,
            "relationship_type": obj.get("relationship_type") or row.relationship_type,
            "source_ref": obj.get("source_ref") or row.source_ref,
            "target_ref": obj.get("target_ref") or row.target_ref,
        })
        if row.start_time:
            obj.setdefault("start_time", _timestamp_text(row.start_time))
        if row.stop_time:
            obj.setdefault("stop_time", _timestamp_text(row.stop_time))
        try:
            normalized = normalize_stix_object(obj, platform_created_at=row.created_at_platform)
        except (TypeError, ValueError) as exc:
            errors.append(f"{models.StixRelationship.__tablename__}:{row.id} ({row.stix_id}): {exc}")
            continue
        if normalized != old_raw:
            changes.append({
                "table": models.StixRelationship.__tablename__,
                "row_id": row.id,
                "stix_id": row.stix_id,
                "old_raw": old_raw,
                "new_raw": normalized,
                "row": row,
            })
    return changes, errors


def _write_backup(path, changes):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump([
            {key: item[key] for key in ("table", "row_id", "stix_id", "old_raw", "new_raw")}
            for item in changes
        ], output, indent=2, default=str, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def migrate(apply=False, backup=None):
    if apply and not backup:
        raise ValueError("--backup is required with --apply")

    if apply:
        with db.session.begin():
            db.session.execute(text("SET LOCAL lock_timeout = '10s'"))
            table_names = [model.__tablename__ for model, _ in MODEL_TYPES]
            table_names.append(models.StixRelationship.__tablename__)
            db.session.execute(text(
                "LOCK TABLE " + ", ".join(table_names) + " IN ACCESS EXCLUSIVE MODE"
            ))
            changes, errors = _changes()
            if errors:
                raise RuntimeError("Migration has invalid rows; no data changed:\n" + "\n".join(errors))
            _write_backup(backup, changes)
            for change in changes:
                change["row"].raw = change["new_raw"]
    else:
        changes, errors = _changes()
        db.session.rollback()

    return len(changes), errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply normalized STIX payloads")
    parser.add_argument("--backup", help="new JSON backup path required with --apply")
    args = parser.parse_args()
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    with app.app_context():
        changed, errors = migrate(apply=args.apply, backup=args.backup)
        print(f"Rows needing normalization: {changed}")
        if errors:
            print(f"Rows with errors: {len(errors)}")
            for error in errors:
                print(error)
            raise SystemExit(1)
        print("Migration applied." if args.apply else "Dry run only; no data changed.")


if __name__ == "__main__":
    main()