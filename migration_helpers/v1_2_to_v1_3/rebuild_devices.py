"""Rebuild device identities from stored fingerprints. Dry-run by default.

Use during the v1.2 to v1.3 migration. Applying requires a full database dump
and a separate JSON backup path. Stop collection and workers before applying.
"""

import argparse
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone

from flask import Flask
from sqlalchemy import delete, inspect, select, text, update

from models import Fingerprint, Heartbeat, Session
from models.associations import BrowserSession, SessionURL
from models.behavioral_event import TYPED_EVENT_MODELS
from models.device import Device, DeviceCookie
from models.rule import RuleMatch
from services.database import db
from services.device_matching import (
    CANONICAL_FIELDS, _apply_canonical_fields, _best_of, _record_ip,
    assess_match, derive_device_type, make_bucket,
)


def plan_rebuild(readings, sessions):
    devices, cookies, assignments = [], {}, {}
    session_clusters = defaultdict(set)
    for reading in readings:
        data = reading["data"]
        if not isinstance(data, dict):
            raise ValueError(f"Fingerprint {reading['id']} has invalid data")
        timestamp = float(reading["timestamp"] or 0)
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError(f"Fingerprint {reading['id']} has an invalid timestamp")
        denorm = Fingerprint.extract_fields(data)
        extensions = data.get("_extensions") or {}
        cookie = (extensions.get("device_id") or {}).get("uuid")
        if cookie is not None and (not isinstance(cookie, str) or len(cookie) > 64):
            raise ValueError(f"Fingerprint {reading['id']} has an invalid UUID")
        client_ip = (extensions.get("ip") or {}).get("ip")
        evidence = {}
        if cookie and cookie in cookies:
            alias = cookies[cookie]
            cluster = alias["cluster"]
            device = devices[cluster]
            confidence = alias["match_confidence"]
        else:
            device, confidence = _best_of(devices, denorm, client_ip)
            if device is None:
                profile = {key: denorm.get(key) for _attr, key in CANONICAL_FIELDS}
                profile["browser_user_agent"] = denorm.get("browser_user_agent", "")
                device = Device(
                    device_bucket=make_bucket(denorm), first_seen=timestamp,
                    recent_ips=[], match_profile=profile,
                )
                _apply_canonical_fields(device, denorm)
                devices.append(device)
                confidence, method = 1.0, "created"
            else:
                evidence = assess_match(device, denorm)
                method = "fuzzy"
            cluster = devices.index(device)
            if cookie:
                cookies[cookie] = {
                    "cluster": cluster, "cookie_id": cookie,
                    "first_seen": timestamp, "match_confidence": confidence,
                    "match_method": method, "match_evidence": evidence,
                }
        if cookie:
            cookies[cookie]["last_seen"] = timestamp
            if not device.cookie_id:
                device.cookie_id = cookie
        _record_ip(device, client_ip)
        device.last_seen = timestamp
        device.confidence = confidence
        is_mobile, device_type = derive_device_type(denorm)
        if device_type != "unknown":
            device.is_mobile, device.device_type = is_mobile, device_type
        assignments[reading["session_id"]] = cluster
        session_clusters[reading["session_id"]].add(cluster)

    for session in sessions:
        cluster = assignments.get(session["id"])
        if cluster is not None:
            device = devices[cluster]
            _record_ip(device, session["client_ip"])
            device.last_seen = max(device.last_seen, session["last_seen"] or 0)
    return devices, cookies, assignments, session_clusters


def prepare_rebuild(readings, sessions, prune_ambiguous=False):
    initial = plan_rebuild(readings, sessions)
    initial_spans = {
        session_id: clusters
        for session_id, clusters in initial[3].items()
        if len(clusters) > 1
    }
    if not prune_ambiguous or not initial_spans:
        return (*initial, [], initial_spans)

    pruned_ids = set(initial_spans)
    remaining_sessions = [row for row in sessions if row["id"] not in pruned_ids]
    remaining_readings = [row for row in readings if row["session_id"] not in pruned_ids]
    rebuilt = plan_rebuild(remaining_readings, remaining_sessions)
    remaining_spans = {
        session_id: clusters
        for session_id, clusters in rebuilt[3].items()
        if len(clusters) > 1
    }
    if remaining_spans:
        raise RuntimeError(
            "Ambiguous session assignments remain after pruning; refusing rebuild: "
            f"{sorted(remaining_spans)}"
        )
    return (*rebuilt, sorted(pruned_ids), initial_spans)


def session_child_counts(session_ids):
    if not session_ids:
        return {}
    child_models = [Fingerprint, Heartbeat, *TYPED_EVENT_MODELS.values(),
                    SessionURL, BrowserSession, RuleMatch]
    return {
        model.__tablename__: model.query.filter(model.session_id.in_(session_ids)).count()
        for model in child_models
    }


def delete_sessions_with_children(session_ids):
    if not session_ids:
        return {}
    child_models = [Fingerprint, Heartbeat, *TYPED_EVENT_MODELS.values(),
                    SessionURL, BrowserSession, RuleMatch]
    deleted = session_child_counts(session_ids)
    for model in child_models:
        query = model.query.filter(model.session_id.in_(session_ids))
        query.delete(synchronize_session=False)
    db.session.execute(delete(Session).where(Session.id.in_(session_ids)))
    return deleted


def write_json(path, contents):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(contents, output, indent=2, default=str, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def rebuild(apply=False, backup=None, prune_ambiguous=False):
    with db.session.begin():
        if apply:
            db.session.execute(text("SET LOCAL lock_timeout = '10s'"))
            db.session.execute(text(
                "LOCK TABLE sessions, fingerprints, heartbeats, beh_copy, beh_paste, "
                "beh_form_submit, beh_button_click, beh_auth_attempt, session_urls, "
                "browser_sessions, rule_matches, devices, device_cookies "
                "IN ACCESS EXCLUSIVE MODE"
            ))
            inspector = inspect(db.session.connection())
            required = {
                "devices": {"cpu_count", "memory", "match_profile"},
                "device_cookies": {"match_method", "match_confidence", "match_evidence"},
            }
            for table, columns in required.items():
                missing = columns - {column["name"] for column in inspector.get_columns(table)}
                if missing:
                    raise RuntimeError(f"Deploy updated schema first: {table} lacks {sorted(missing)}")
        else:
            db.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))

        sessions = db.session.execute(select(
            Session.id, Session.device_id, Session.client_ip, Session.last_seen,
        ).order_by(Session.id)).mappings().all()
        readings = db.session.execute(select(
            Fingerprint.id, Fingerprint.session_id, Fingerprint.timestamp, Fingerprint.data,
        ).order_by(Fingerprint.timestamp, Fingerprint.id)).mappings().all()
        old_devices = db.session.execute(text("SELECT * FROM devices ORDER BY id")).mappings().all()
        old_cookies = db.session.execute(text("SELECT * FROM device_cookies ORDER BY id")).mappings().all()
        if not readings:
            raise RuntimeError("No stored fingerprints; refusing an empty rebuild")
        devices, cookies, assignments, session_clusters, pruned_ids, ambiguous_sessions = prepare_rebuild(
            readings, sessions, prune_ambiguous=prune_ambiguous,
        )
        if apply and ambiguous_sessions and not prune_ambiguous:
            raise RuntimeError(
                "Ambiguous sessions span multiple planned devices; rerun with "
                "--prune-ambiguous to delete those sessions and their child data"
            )
        pruned_session_rows = []
        fingerprints_pruned = 0
        if pruned_ids:
            pruned_session_rows = db.session.execute(select(
                Session.id, Session.visit_id, Session.fsid, Session.risk_score,
                Session.flags, Session.client_ip, Session.authenticated,
                Session.domains, Session.device_id, Session.first_seen, Session.last_seen,
            ).where(Session.id.in_(pruned_ids))).mappings().all()
            fingerprints_pruned = sum(row["session_id"] in pruned_ids for row in readings)
        pruned_child_rows = session_child_counts(pruned_ids)
        report = {
            "mode": "apply" if apply else "dry-run",
            "fingerprints_replayed": len(readings) - fingerprints_pruned,
            "sessions_before_prune": len(sessions), "sessions": len(sessions) - len(pruned_ids),
            "old_devices": len(old_devices), "new_devices": len(devices),
            "old_aliases": len(old_cookies), "new_aliases": len(cookies),
            "ambiguous_sessions_detected": {
                str(session_id): sorted(clusters)
                for session_id, clusters in ambiguous_sessions.items()
            },
            "pruned_session_ids": pruned_ids,
            "fingerprints_pruned": fingerprints_pruned,
            "pruned_child_rows": pruned_child_rows,
            "sessions_without_fingerprints": [
                row["id"] for row in sessions
                if row["id"] not in pruned_ids and row["id"] not in assignments
            ],
            "sessions_spanning_multiple_devices": {
                str(session_id): sorted(clusters)
                for session_id, clusters in session_clusters.items() if len(clusters) > 1
            },
            "cluster_numbers_are_zero_based_plan_indexes": True,
        }
        old_to_new = defaultdict(set)
        for session in sessions:
            if session["device_id"] is not None and session["id"] in assignments:
                old_to_new[session["device_id"]].add(assignments[session["id"]])
        report["old_device_to_planned_clusters"] = {
            str(old_id): sorted(clusters) for old_id, clusters in old_to_new.items()
        }

        if apply:
            write_json(backup, {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "devices": [dict(row) for row in old_devices],
                "device_cookies": [dict(row) for row in old_cookies],
                "session_assignments": [dict(row) for row in sessions],
                "pruned_sessions": [dict(row) for row in pruned_session_rows],
                "pruned_child_rows": pruned_child_rows,
                "rebuild_report": report,
            })
            delete_sessions_with_children(pruned_ids)
            db.session.execute(update(Session).values(device_id=None))
            db.session.execute(delete(DeviceCookie))
            db.session.execute(delete(Device))
            db.session.add_all(devices)
            db.session.flush()
            db.session.add_all([
                DeviceCookie(
                    device_id=devices[alias["cluster"]].id,
                    **{key: value for key, value in alias.items() if key != "cluster"},
                ) for alias in cookies.values()
            ])
            for session_id, cluster in assignments.items():
                db.session.execute(update(Session).where(Session.id == session_id).values(
                    device_id=devices[cluster].id,
                ))
            db.session.flush()
            report["planned_cluster_to_device_id"] = {
                str(cluster): device.id for cluster, device in enumerate(devices)
            }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Replace device rows and aliases in one transaction")
    parser.add_argument("--backup", help="New JSON backup file; mandatory with --apply, never overwritten")
    parser.add_argument(
        "--prune-ambiguous", action="store_true",
        help="Delete sessions spanning multiple planned devices and all their child records",
    )
    arguments = parser.parse_args()
    if arguments.apply and not arguments.backup:
        parser.error("--apply requires --backup; take a full database backup as well")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL must be configured explicitly")
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=database_url, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        try:
            print(json.dumps(rebuild(
                apply=arguments.apply, backup=arguments.backup,
                prune_ambiguous=arguments.prune_ambiguous,
            ), indent=2))
        except Exception as error:
            parser.exit(1, f"Rebuild failed; transaction rolled back: {error}\n")


if __name__ == "__main__":
    main()