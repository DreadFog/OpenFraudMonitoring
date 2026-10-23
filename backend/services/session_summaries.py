"""Bounded, page-wide reads for session list summaries."""

from sqlalchemy import func

from models import Fingerprint, Heartbeat
from models.associations import BrowserSession, SessionURL
from models.behavioral_event import TYPED_EVENT_MODELS
from services.database import db


def _counts(model, session_ids):
    return dict(
        db.session.query(model.session_id, func.count(model.id))
        .filter(model.session_id.in_(session_ids))
        .group_by(model.session_id)
        .all()
    )


def _ranked_values(model, value_column, session_ids, limit, ordering):
    ranked = (
        db.session.query(
            model.session_id.label("session_id"),
            value_column.label("value"),
            func.row_number().over(
                partition_by=model.session_id, order_by=ordering,
            ).label("position"),
        )
        .filter(model.session_id.in_(session_ids))
        .subquery()
    )
    return (
        db.session.query(ranked.c.session_id, ranked.c.value)
        .filter(ranked.c.position <= limit)
        .order_by(ranked.c.session_id, ranked.c.position)
        .all()
    )


def session_summaries(session_ids):
    """Load counts and bounded preview values without per-session queries."""
    if not session_ids:
        return {}
    summaries = {
        session_id: {
            "fingerprint": {}, "urls": [], "session_ids": [],
            "urls_count": 0, "heartbeats": 0, "behavioral_events": 0,
        }
        for session_id in session_ids
    }
    for model, key in ((SessionURL, "urls_count"), (Heartbeat, "heartbeats")):
        for session_id, count in _counts(model, session_ids).items():
            summaries[session_id][key] = count
    for model in TYPED_EVENT_MODELS.values():
        for session_id, count in _counts(model, session_ids).items():
            summaries[session_id]["behavioral_events"] += count
    for session_id, data in _ranked_values(
        Fingerprint, Fingerprint.data, session_ids, 1,
        (Fingerprint.timestamp.desc(), Fingerprint.id.desc()),
    ):
        summaries[session_id]["fingerprint"] = data or {}
    for model, column, key, limit in (
        (SessionURL, SessionURL.url, "urls", 3),
        (BrowserSession, BrowserSession.browser_session_id, "session_ids", 2),
    ):
        for session_id, value in _ranked_values(model, column, session_ids, limit, model.id.asc()):
            summaries[session_id][key].append(value)
    return summaries
