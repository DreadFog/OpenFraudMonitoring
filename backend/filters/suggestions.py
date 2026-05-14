"""Suggestion helpers for custom filters."""


def suggest_as(q: str) -> list[str]:
    """Suggest AS numbers from the STIX store."""
    from models import StixAutonomousSystem

    query = StixAutonomousSystem.query
    if q:
        query = query.filter(StixAutonomousSystem.value.ilike(f"%{q}%"))
    rows = query.order_by(StixAutonomousSystem.value).limit(20).all()
    return [r.value for r in rows]


def suggest_country(q: str) -> list[str]:
    """Suggest country codes from the STIX store."""
    from models import StixCountry

    query = StixCountry.query
    if q:
        query = query.filter(StixCountry.value.ilike(f"%{q}%"))
    rows = query.order_by(StixCountry.value).limit(20).all()
    return [r.value for r in rows]


def suggest_behavior_data(event_type: str, key: str, q: str) -> list[str]:
    """Suggest distinct values from behavioral event JSON payload data."""
    from services.database import db
    from models import BehavioralEvent

    expr = BehavioralEvent.data[key].astext
    query = db.session.query(expr.distinct()).filter(
        BehavioralEvent.event_type == event_type,
        expr != None,  # noqa: E711
        expr != "",
    )
    if q:
        query = query.filter(expr.ilike(f"%{q}%"))
    rows = query.order_by(expr).limit(20).all()
    return [r[0] for r in rows if r and r[0]]


def suggest_behavior_button_text(q: str) -> list[str]:
    return suggest_behavior_data("button_click", "text", q)


def suggest_behavior_form_action(q: str) -> list[str]:
    return suggest_behavior_data("form_submit", "action", q)


def suggest_behavior_form_method(q: str) -> list[str]:
    return suggest_behavior_data("form_submit", "method", q)


def suggest_behavior_event_url(q: str) -> list[str]:
    """Suggest distinct behavioral event URLs."""
    from models import BehavioralEvent

    query = BehavioralEvent.query.with_entities(BehavioralEvent.url.distinct()).filter(
        BehavioralEvent.url != "",
    )
    if q:
        query = query.filter(BehavioralEvent.url.ilike(f"%{q}%"))
    rows = query.order_by(BehavioralEvent.url).limit(20).all()
    return [r[0] for r in rows if r and r[0]]
