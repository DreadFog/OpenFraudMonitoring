"""
Rule evaluation engine - builds SQLAlchemy queries from filter conditions.

Used by:
- Frontend session filtering (routes/sessions.py)
- Rule evaluation in the worker (worker.py)
- Rule CRUD validation (routes/rules.py)

Sequence conditions
-------------------
A rule's conditions list may contain one or more "sequence" conditions alongside
regular {field, op, value} conditions.  A sequence condition has the form:

    {
        "type": "sequence",
        "steps": [
            {"event_type": "paste",       "filters": [{"field": "target_name", "op": "eq", "value": "password"}]},
            {"event_type": "form_submit", "filters": [{"field": "field_names",  "op": "contains", "value": "password"}]}
        ]
    }

Sequence conditions are only valid in *periodic* rules and are evaluated in
Python after the SQL phase has produced a candidate set of sessions.  Each
step must be satisfied (in order) by a real event in the session's event
timeline.

Supported step filter fields (mapped to typed model columns):
  copy        — url, length, source_tag, source_id, source_name, source_type, form_action
  paste       — url, length, target_tag, target_id, target_name, target_type, form_action
  form_submit — url, action, method, field_names (supports contains/eq/starts_with/ends_with)
  button_click — url, x, y, tag, text
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

    Sequence conditions (type == "sequence") are silently skipped here — they
    are handled separately by evaluate_rule after the SQL phase.

    Each filter condition targeting a Fingerprint field is wrapped in an EXISTS
    subquery so that the result is always a set of Session rows.

    Custom filters (registered in filters/ package) are dispatched to their
    handler functions instead of being resolved via model column.

    Args:
        filters: list of {"field": str, "op": str, "value": str} or sequence dicts
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
        # Skip sequence conditions — evaluated in Python after SQL phase
        if f.get("type") == "sequence":
            continue

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


# ─────────────────────────────────────────────────────────────────────────────
# Sequence evaluation (Python-side, periodic rules only)
# ─────────────────────────────────────────────────────────────────────────────

def get_session_events_sorted(session_id: int) -> list[dict]:
    """Return all typed behavioral events for a session, sorted by timestamp.

    Each event is a plain dict with at minimum {event_type, timestamp} plus all
    columns of the typed model.
    """
    from models import CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent

    events: list[dict] = []
    for Model in (CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent):
        rows = Model.query.filter_by(session_id=session_id).all()
        for row in rows:
            events.append(row.to_dict())

    events.sort(key=lambda e: e.get("timestamp") or 0)
    return events


def _match_step_filter(event: dict, f: dict) -> bool:
    """Return True if a single step filter matches an event dict."""
    field = f.get("field", "")
    op = f.get("op", "eq")
    value = str(f.get("value", ""))
    raw = event.get(field)

    # Special handling for field_names (list)
    if field == "field_names":
        names = raw if isinstance(raw, list) else []
        str_names = [str(n) for n in names]
        if op == "eq":
            return value in str_names
        if op == "neq":
            return value not in str_names
        if op == "contains":
            return any(value.lower() in n.lower() for n in str_names)
        if op == "not_contains":
            return all(value.lower() not in n.lower() for n in str_names)
        if op == "starts_with":
            return any(n.lower().startswith(value.lower()) for n in str_names)
        if op == "ends_with":
            return any(n.lower().endswith(value.lower()) for n in str_names)
        return False

    if raw is None:
        return False
    val_str = str(raw).lower()
    value_lower = value.lower()

    if op == "eq":
        return val_str == value_lower
    if op == "neq":
        return val_str != value_lower
    if op == "contains":
        return value_lower in val_str
    if op == "not_contains":
        return value_lower not in val_str
    if op == "starts_with":
        return val_str.startswith(value_lower)
    if op == "ends_with":
        return val_str.endswith(value_lower)
    if op in ("gt", "gte", "lt", "lte"):
        try:
            rv, vv = float(raw), float(value)
            return {"gt": rv > vv, "gte": rv >= vv, "lt": rv < vv, "lte": rv <= vv}[op]
        except (ValueError, TypeError):
            return False
    return False


def _match_step(event: dict, step: dict) -> bool:
    """Return True if an event satisfies all filters in a sequence step."""
    if event.get("event_type") != step.get("event_type"):
        return False
    for f in step.get("filters") or []:
        if not _match_step_filter(event, f):
            return False
    return True


def evaluate_sequence_condition(events: list[dict], seq_condition: dict) -> bool:
    """Return True if the ordered events satisfy all steps in seq_condition.

    Uses a greedy left-to-right scan: advances to the next step whenever the
    current event matches, so it finds the first valid subsequence in O(n).
    """
    steps = seq_condition.get("steps") or []
    if not steps:
        return True  # empty sequence always matches

    step_idx = 0
    for event in events:
        if _match_step(event, steps[step_idx]):
            step_idx += 1
            if step_idx == len(steps):
                return True  # all steps satisfied in order
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Rule evaluation entry point
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_rule(rule, session_id=None, base_query=None):
    """
    Evaluate a Rule model instance against sessions.

    Flow:
    1. SQL phase  — build_session_query on the non-sequence conditions to get
                    candidate sessions.
    2. Sequence phase (optional) — for rules that include sequence conditions,
                    further filter candidates by running the Python-side sequence
                    evaluator against each session's full event timeline.

    Args:
        rule:       Rule model instance (must have .conditions, .logic)
        session_id: optional – scope evaluation to a single session (DB primary key)
        base_query: optional – pre-filtered Session query (e.g. last_seen >= t)

    Returns:
        list of matching Session objects
    """
    Session = _get_model("Session")
    conditions = rule.conditions or []

    seq_conditions = [c for c in conditions if c.get("type") == "sequence"]
    sql_conditions = [c for c in conditions if c.get("type") != "sequence"]

    # ── SQL phase ─────────────────────────────────────────────────────────────
    if base_query is None:
        base_query = Session.query
    if session_id is not None:
        base_query = base_query.filter(Session.id == session_id)

    candidates = build_session_query(
        sql_conditions,
        logic=rule.logic or "AND",
        base_query=base_query,
    ).all()

    if not seq_conditions:
        return candidates

    # ── Sequence phase ────────────────────────────────────────────────────────
    # All sequence conditions must match (AND semantics — sequence rules require
    # AND logic, validated at rule creation in routes/rules.py).
    matched = []
    for sess in candidates:
        events = get_session_events_sorted(sess.id)
        if all(evaluate_sequence_condition(events, sc) for sc in seq_conditions):
            matched.append(sess)
    return matched



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
