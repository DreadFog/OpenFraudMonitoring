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


def _suggest_typed_column(Model, column_name: str, q: str) -> list[str]:
    """Suggest distinct non-empty values from a typed event model column."""
    from services.database import db

    column = getattr(Model, column_name)
    query = db.session.query(column.distinct()).filter(
        column != None,   # noqa: E711
        column != "",
    )
    if q:
        query = query.filter(column.ilike(f"%{q}%"))
    rows = query.order_by(column).limit(20).all()
    return [r[0] for r in rows if r and r[0]]


def suggest_behavior_button_text(q: str) -> list[str]:
    from models import ButtonClickEvent
    return _suggest_typed_column(ButtonClickEvent, "text", q)


def suggest_behavior_form_action(q: str) -> list[str]:
    from models import FormSubmitEvent
    return _suggest_typed_column(FormSubmitEvent, "action", q)


def suggest_behavior_form_method(q: str) -> list[str]:
    from models import FormSubmitEvent
    return _suggest_typed_column(FormSubmitEvent, "method", q)


def suggest_behavior_event_url(q: str) -> list[str]:
    """Suggest distinct behavioral event URLs across all typed event tables."""
    from models import CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent
    from services.database import db
    from sqlalchemy import union_all, literal_column, select

    seen: set[str] = set()
    results: list[str] = []
    for Model in (CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent):
        for row in _suggest_typed_column(Model, "url", q):
            if row not in seen:
                seen.add(row)
                results.append(row)
        if len(results) >= 20:
            break
    return results[:20]


def suggest_behavior_form_field_name(q: str) -> list[str]:
    """Suggest distinct field names from form_submit field_names arrays."""
    from models import FormSubmitEvent
    from services.database import db
    from sqlalchemy import func

    elem = func.jsonb_array_elements_text(FormSubmitEvent.field_names).column_valued("elem")
    query = db.session.query(elem.distinct())
    if q:
        query = query.filter(elem.ilike(f"%{q}%"))
    rows = query.order_by(elem).limit(20).all()
    return [r[0] for r in rows if r and r[0]]


def suggest_behavior_paste_target_name(q: str) -> list[str]:
    from models import PasteEvent
    return _suggest_typed_column(PasteEvent, "target_name", q)


def suggest_behavior_copy_source_name(q: str) -> list[str]:
    from models import CopyEvent
    return _suggest_typed_column(CopyEvent, "source_name", q)
