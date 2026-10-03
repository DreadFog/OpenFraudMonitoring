from uuid import UUID

from sqlalchemy.exc import IntegrityError

from services.database import db


def normalize_visit_id(value):
    """Return a canonical UUID string or None for an invalid visit token."""
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def get_or_create_visit(visit_id, fsid, timestamp):
    from models import Session

    session = Session.query.filter_by(visit_id=visit_id).first()
    if session is not None:
        return session

    session = Session(visit_id=visit_id, fsid=fsid, first_seen=timestamp)
    db.session.add(session)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        session = Session.query.filter_by(visit_id=visit_id).first()
        if session is None:
            raise
    return session