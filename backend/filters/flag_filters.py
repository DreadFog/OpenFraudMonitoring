"""Custom filter for session triggered-flag membership.

Supports filtering sessions by whether a specific rule flag is present in (or
absent from) the ``session.flags`` JSONB string array.
"""

from .registry import register_custom_filter


# ─────────────────────────────────────────────────────────────────────────────
# Handler
# ─────────────────────────────────────────────────────────────────────────────

def _flag_handler(query, op, value):
    """Filter sessions where ``flags`` contains (or does not contain) *value*."""
    from models import Session

    if not value:
        return query.filter(False)

    contains_cond = Session.flags.contains([value])

    if op == "eq":
        return query.filter(contains_cond)
    elif op == "neq":
        return query.filter(~contains_cond)
    return query.filter(False)


# ─────────────────────────────────────────────────────────────────────────────
# Suggest
# ─────────────────────────────────────────────────────────────────────────────

def _flag_suggest(q: str) -> list[str]:
    """Return rule names matching *q* for autocomplete."""
    from models.rule import Rule

    query = Rule.query.with_entities(Rule.name)
    if q:
        query = query.filter(Rule.name.ilike(f"%{q}%"))
    rows = query.order_by(Rule.name).limit(20).all()
    return [r[0] for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate
# ─────────────────────────────────────────────────────────────────────────────

def _flag_aggregate(session_ids, limit: int):
    """Count how many sessions in *session_ids* have each flag value."""
    from collections import Counter
    from models import Session

    rows = (
        Session.query
        .filter(Session.id.in_(session_ids))
        .with_entities(Session.flags)
        .all()
    )
    counter = Counter()
    for (flags,) in rows:
        if flags:
            for flag in flags:
                counter[flag] += 1

    return [
        {"value": flag, "count": count}
        for flag, count in counter.most_common(limit)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

def register_filters():
    register_custom_filter(
        name="triggered_flag",
        label="Triggered Flag",
        field_type="string",
        handler=_flag_handler,
        suggest=_flag_suggest,
        aggregate=_flag_aggregate,
        category="Session Metadata",
    )
