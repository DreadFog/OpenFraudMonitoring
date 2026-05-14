"""
Rule evaluation engine - builds SQLAlchemy queries from filter conditions.

Used by:
- Frontend session filtering (routes/sessions.py)
- Rule evaluation in the worker (worker.py)
- Rule CRUD validation (routes/rules.py)
"""

from sqlalchemy import and_, or_
from services.schema import get_field_meta
from filters import get_custom_handler

# Lazy model resolution to avoid circular imports
_models = {}


def _get_model(name):
    if not _models:
        from models import Session, Fingerprint
        _models["Session"] = Session
        _models["Fingerprint"] = Fingerprint
    return _models[name]


def build_condition(field_meta, op, value):
    """Build a single SQLAlchemy filter condition from field metadata + operator + value."""
    model = _get_model(field_meta["model"])
    column = getattr(model, field_meta["column"])
    field_type = field_meta["type"]

    # Cast value to the appropriate Python type
    if field_type in ("number", "date"):
        try:
            value = float(value)
        except (ValueError, TypeError):
            return None
    elif field_type == "boolean":
        value = str(value).lower() in ("true", "1", "yes")

    if op == "eq":
        return column == value
    elif op == "neq":
        return column != value
    elif op == "contains":
        return column.ilike(f"%{value}%")
    elif op == "not_contains":
        return ~column.ilike(f"%{value}%")
    elif op == "starts_with":
        return column.ilike(f"{value}%")
    elif op == "ends_with":
        return column.ilike(f"%{value}")
    elif op == "gt":
        return column > value
    elif op == "gte":
        return column >= value
    elif op == "lt":
        return column < value
    elif op == "lte":
        return column <= value

    return None


def build_session_query(filters, logic="AND", base_query=None):
    """
    Build a Session query with the given filter conditions applied.

    Each filter condition targeting a Fingerprint field is wrapped in an EXISTS
    subquery so that the result is always a set of Session rows.

    Custom filters (registered in filters/ package) are dispatched to their
    handler functions instead of being resolved via model column.

    Args:
        filters: list of {"field": str, "op": str, "value": str}
        logic: "AND" or "OR" – how to combine conditions
        base_query: optional starting query (defaults to Session.query)

    Returns:
        SQLAlchemy query on Session
    """
    from services.database import db

    Session = _get_model("Session")
    Fingerprint = _get_model("Fingerprint")

    query = base_query if base_query is not None else Session.query
    combiner = and_ if logic == "AND" else or_

    all_conditions = []
    # Custom filters that need post-processing (they mutate the query directly)
    deferred_handlers = []

    for f in filters:
        field_name = f.get("field", "")
        op = f.get("op", "")
        value = f.get("value", "")

        # Check for a custom filter handler first
        handler = get_custom_handler(field_name)
        if handler is not None:
            deferred_handlers.append((handler, op, value))
            continue

        # Regular schema-based filters
        meta = get_field_meta(field_name)
        if not meta:
            continue

        cond = build_condition(meta, op, value)
        if cond is None:
            continue

        if meta["model"] == "Session":
            all_conditions.append(cond)
        else:
            # Wrap fingerprint-level condition in an EXISTS subquery
            fp_exists = db.session.query(Fingerprint.id).filter(
                Fingerprint.session_id == Session.id,
                cond,
            ).exists()
            all_conditions.append(fp_exists)

    if all_conditions:
        query = query.filter(combiner(*all_conditions))

    # Apply custom filter handlers (they receive and return the query)
    for handler, op, value in deferred_handlers:
        query = handler(query, op, value)

    return query


def evaluate_rule(rule, session_id=None):
    """
    Evaluate a Rule model instance against sessions.

    Args:
        rule: Rule model instance (must have .conditions, .logic)
        session_id: optional – scope evaluation to a single session (DB primary key)

    Returns:
        list of matching Session objects
    """
    Session = _get_model("Session")

    base = Session.query
    if session_id is not None:
        base = base.filter(Session.id == session_id)

    query = build_session_query(
        rule.conditions or [],
        logic=rule.logic or "AND",
        base_query=base,
    )

    return query.all()
