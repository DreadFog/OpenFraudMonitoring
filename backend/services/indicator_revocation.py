from datetime import datetime, timedelta, timezone

from services.database import db
from services.settings import INDICATOR_REVOCATION_DAYS_KEY, get_global_setting


def get_revocation_days():
    return get_global_setting(INDICATOR_REVOCATION_DAYS_KEY)


def refresh_indicator_revocation(commit=True):
    from models import StixIndicator
    return apply_indicator_revocation(StixIndicator.query.yield_per(500), commit=commit)


def apply_indicator_revocation(rows, days=None, now=None, commit=True):
    if days is None:
        days = get_revocation_days()
    now = now or datetime.now(timezone.utc)
    threshold = now.astimezone(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    changed = False
    for row in rows:
        if not row.stix_id.startswith("indicator--"):
            continue
        refreshed = row.last_refreshed_at or row.created_at_platform
        if refreshed and refreshed.tzinfo is not None:
            refreshed = refreshed.astimezone(timezone.utc).replace(tzinfo=None)
        raw = row.raw or {}
        if raw.get("valid_until"):
            from services.indicator_generation import parse_timestamp
            expired = parse_timestamp(raw["valid_until"]) <= now
        else:
            expired = bool(refreshed and refreshed <= threshold)
        revoked = bool(raw.get("revoked") or expired)
        if row.revoked != revoked:
            row.revoked = revoked
            changed = True
    if changed and commit:
        db.session.commit()
    return changed