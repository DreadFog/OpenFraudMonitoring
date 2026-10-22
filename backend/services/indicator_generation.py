"""Create IP indicators and renew related indicators from qualifying activity."""

import ipaddress
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func

from models import Session, StixIndicator, StixRelationship
from services.database import db
from services.settings import INDICATOR_AUTOMATION_KEY, get_global_setting
from services.stix_filters import TYPE_TO_MODEL
from services.stix_objects import normalize_stix_object


logger = logging.getLogger(__name__)
IP_TYPES = ("ipv4-addr", "ipv6-addr")


def parse_timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def format_timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def revoked_after(raw, observed_at):
    """True when an explicit revocation is newer than the qualifying activity."""
    if raw.get("revoked") is not True or not raw.get("modified"):
        return False
    try:
        return parse_timestamp(raw["modified"]) >= observed_at
    except (AttributeError, TypeError, ValueError):
        return False


def renew_indicator(row, observed_at, validity_hours, now, override_revocation=False):
    raw = dict(row.raw or {})
    if not override_revocation and revoked_after(raw, observed_at):
        return False
    expiry = observed_at + timedelta(hours=validity_hours)
    previous = parse_timestamp(raw["valid_until"]) if raw.get("valid_until") else None
    if previous is not None:
        expiry = max(expiry, previous)
    valid_from = parse_timestamp(raw["valid_from"]) if raw.get("valid_from") else observed_at
    if expiry <= valid_from:
        raise ValueError(f"Indicator {row.stix_id} has a validity start after the requested expiry")
    refreshed = row.last_refreshed_at
    if refreshed is not None:
        refreshed = refreshed.replace(tzinfo=timezone.utc) if refreshed.tzinfo is None else refreshed.astimezone(timezone.utc)
    if previous == expiry and not raw.get("revoked") and not row.revoked and refreshed and refreshed >= observed_at:
        return False
    raw.update({
        "valid_from": format_timestamp(valid_from),
        "valid_until": format_timestamp(expiry),
        "modified": format_timestamp(now),
        "revoked": False,
    })
    row.raw = raw
    row.revoked = False
    row.last_refreshed_at = max(observed_at, refreshed or observed_at).replace(tzinfo=None)
    return True


def ensure_ip_indicators(stix_type, observable_id, observed_at, validity_hours=24, now=None,
                         override_revocation=False):
    """Caller owns the transaction; locking the observable serializes creators.

    Automatic callers only reactivate indicators revoked before the activity;
    manual callers pass override_revocation=True.
    """
    if stix_type not in IP_TYPES:
        raise ValueError("Only IPv4 and IPv6 observables support indicator creation")
    now = now or datetime.now(timezone.utc)
    observed_at = observed_at.replace(microsecond=observed_at.microsecond // 1000 * 1000)
    model = TYPE_TO_MODEL[stix_type]
    observable = model.query.filter_by(id=observable_id).with_for_update().first()
    if observable is None:
        raise LookupError("Observable not found")
    address = ipaddress.ip_address(observable.value)
    if "%" in observable.value or f"ipv{address.version}-addr" != stix_type:
        raise ValueError("Observable must contain an IP address of the selected family")
    related_ids = db.session.query(StixRelationship.source_ref).filter_by(
        relationship_type="based-on", target_ref=observable.stix_id,
    )
    indicators = StixIndicator.query.filter(
        StixIndicator.stix_id.in_(related_ids),
    ).order_by(StixIndicator.stix_id).with_for_update().all()
    created = not indicators
    if created:
        pattern = f"[{stix_type}:value = '{address}']"
        sid = f"indicator--{uuid4()}"
        raw = normalize_stix_object({
            "type": "indicator", "id": sid, "name": str(address),
            "description": "IP indicator created by OpenFraudMonitoring.",
            "pattern_type": "stix", "pattern": pattern,
            "indicator_types": ["malicious-activity"],
            "created": format_timestamp(now), "modified": format_timestamp(now),
            "valid_from": format_timestamp(observed_at),
            "valid_until": format_timestamp(observed_at + timedelta(hours=validity_hours)),
            "revoked": False,
        })
        row = StixIndicator(
            stix_id=sid, value=pattern, name=str(address),
            description=raw["description"], raw=raw, revoked=False,
            last_refreshed_at=observed_at.replace(tzinfo=None),
        )
        db.session.add(row)
        relation_id = f"relationship--{uuid4()}"
        relation = normalize_stix_object({
            "type": "relationship", "id": relation_id,
            "relationship_type": "based-on", "source_ref": sid,
            "target_ref": observable.stix_id,
            "created": format_timestamp(now), "modified": format_timestamp(now),
        })
        db.session.add(StixRelationship(
            stix_id=relation_id, relationship_type="based-on",
            source_ref=sid, target_ref=observable.stix_id, raw=relation,
        ))
        indicators = [row]
    changed = int(created)
    if not created:
        changed = sum(
            renew_indicator(row, observed_at, validity_hours, now, override_revocation)
            for row in indicators
        )
    return indicators, created, changed


def generate_session_indicators(now=None):
    """Scan the rolling recent-activity window after periodic score evaluation."""
    policy = get_global_setting(INDICATOR_AUTOMATION_KEY)
    if not policy["enabled"]:
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=policy["lookback_minutes"])).timestamp() * 1000
    candidates = db.session.query(
        Session.ip_observable_type, Session.ip_observable_id, func.max(Session.last_seen),
    ).filter(
        Session.last_seen >= cutoff,
        Session.last_seen <= now.timestamp() * 1000,
        Session.risk_score >= policy["risk_threshold"],
        Session.ip_observable_type.in_(IP_TYPES),
        Session.ip_observable_id.isnot(None),
    ).group_by(Session.ip_observable_type, Session.ip_observable_id).order_by(
        Session.ip_observable_type, Session.ip_observable_id,
    ).all()
    changed = 0
    try:
        for stix_type, observable_id, last_seen in candidates:
            observed_at = datetime.fromtimestamp(last_seen / 1000, timezone.utc)
            if observed_at + timedelta(hours=policy["validity_hours"]) <= now:
                continue
            _, _, count = ensure_ip_indicators(
                stix_type, observable_id, observed_at, policy["validity_hours"], now=now,
            )
            changed += count
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if changed:
        logger.info("Created/renewed %d IP indicators from %d qualifying observables", changed, len(candidates))
    return changed
