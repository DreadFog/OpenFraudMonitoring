"""Delete inactive visits and entities no retained visit needs."""

from calendar import monthrange
from datetime import datetime, timezone

from sqlalchemy import func, or_, text

from models import (
    Session, Device, StixIPv4Addr, StixIPv6Addr, StixUserAgent,
    StixAutonomousSystem, StixCountry, StixIndicator, StixMalware,
    StixCampaign, StixIntrusionSet, StixRelationship,
)
from models.device import MAX_RECENT_IPS
from services.database import db
from services.settings import (
    DATA_RETENTION_MONTHS_KEY, GLOBAL_DEFAULTS, get_global_setting,
    validate_retention_months,
)

OBSERVABLE_MODELS = (
    (StixIPv4Addr, "ipv4-addr", Session.ip_observable_id),
    (StixIPv6Addr, "ipv6-addr", Session.ip_observable_id),
    (StixUserAgent, "user-agent", Session.user_agent_observable_id),
)
STIX_MODELS = (
    StixIPv4Addr, StixIPv6Addr, StixUserAgent, StixAutonomousSystem,
    StixCountry, StixIndicator, StixMalware, StixCampaign, StixIntrusionSet,
)


def retention_cutoff(now, months):
    """Subtract calendar months in UTC, clamping to the target month's end."""
    month_index = now.year * 12 + now.month - 1 - months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    if year < 1:
        return datetime.min.replace(tzinfo=timezone.utc)
    return now.replace(year=year, month=month,
                       day=min(now.day, monthrange(year, month)[1]))


def _observable_refs(session_query):
    refs = set()
    for model, kind, column in OBSERVABLE_MODELS:
        query = session_query.join(model, model.id == column)
        if kind != "user-agent":
            query = query.filter(Session.ip_observable_type == kind)
        refs.update(ref for ref, in query.with_entities(model.stix_id).distinct())
    return refs


def _related_refs(roots, adjacency, observables):
    """Follow enrichment links without crossing into unrelated session observables."""
    visited = set(roots)
    pending = list(roots)
    while pending:
        current = pending.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor in visited or (neighbor in observables and neighbor not in roots):
                continue
            visited.add(neighbor)
            pending.append(neighbor)
    return visited


def purge_inactive_data(now=None, batch_size=500):
    """Run one transactional sweep; session last_seen is JavaScript milliseconds."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    months = validate_retention_months(get_global_setting(DATA_RETENTION_MONTHS_KEY))
    months = months or GLOBAL_DEFAULTS[DATA_RETENTION_MONTHS_KEY]
    cutoff = retention_cutoff(now, months)
    cutoff_ms = cutoff.timestamp() * 1000
    counts = {"sessions": 0, "devices": 0, "entities": 0, "relationships": 0}
    try:
        if db.engine.dialect.name == "postgresql":
            acquired = db.session.execute(text(
                "SELECT pg_try_advisory_xact_lock(88442212)"
            )).scalar()
            if not acquired:
                db.session.rollback()
                return counts

        expired_refs = set()
        while True:
            expired = Session.query.filter(Session.last_seen < cutoff_ms).order_by(
                Session.id
            ).limit(batch_size).with_for_update().all()
            if not expired:
                break
            session_ids = [session.id for session in expired]
            expired_refs.update(_observable_refs(Session.query.filter(Session.id.in_(session_ids))))
            for session in expired:
                db.session.delete(session)
            db.session.flush()
            counts["sessions"] += len(expired)

        for device in Device.query.with_for_update().yield_per(batch_size):
            last_seen = db.session.query(func.max(Session.last_seen)).filter_by(
                device_id=device.id
            ).scalar()
            if last_seen is None:
                db.session.delete(device)
                counts["devices"] += 1
            else:
                device.last_seen = last_seen
                device.recent_ips = [ip for ip, in db.session.query(Session.client_ip).filter(
                    Session.device_id == device.id, Session.client_ip != "",
                ).group_by(Session.client_ip).order_by(func.max(Session.last_seen).desc()).limit(MAX_RECENT_IPS)]
        db.session.flush()

        entities = {}
        observables = set()
        for model in STIX_MODELS:
            for entity_id, ref, last_activity in db.session.query(
                model.id, model.stix_id,
                func.coalesce(model.last_refreshed_at, model.created_at_platform),
            ):
                entities[ref] = (model, entity_id, last_activity)
                if model in (StixIPv4Addr, StixIPv6Addr, StixUserAgent):
                    observables.add(ref)

        adjacency = {}
        for source, target in db.session.query(StixRelationship.source_ref, StixRelationship.target_ref):
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set()).add(source)
        protected = _related_refs(_observable_refs(Session.query), adjacency, observables)
        expired_related = _related_refs(expired_refs, adjacency, observables)
        stale_refs = {
            ref for ref, (_, _, last_activity) in entities.items()
            if ref not in protected and (
                ref in expired_related or last_activity.replace(tzinfo=timezone.utc) < cutoff
            )
        }
        if stale_refs:
            counts["relationships"] = StixRelationship.query.filter(or_(
                StixRelationship.source_ref.in_(stale_refs),
                StixRelationship.target_ref.in_(stale_refs),
            )).delete(synchronize_session=False)
            for model in STIX_MODELS:
                counts["entities"] += model.query.filter(model.stix_id.in_(stale_refs)).delete(
                    synchronize_session=False
                )
        db.session.commit()
        return counts
    except Exception:
        db.session.rollback()
        raise