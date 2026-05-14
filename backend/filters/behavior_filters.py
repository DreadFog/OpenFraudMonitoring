"""Behavioral-event custom filters and suggestions."""

from sqlalchemy import func

from .registry import register_custom_filter
from .suggestions import (
    suggest_behavior_button_text,
    suggest_behavior_form_action,
    suggest_behavior_form_method,
    suggest_behavior_event_url,
)


def _build_behavior_count_condition(event_type: str, op: str, value):
    """Build scalar count condition for per-session behavioral event totals."""
    from models import Session, BehavioralEvent

    try:
        target = int(float(value))
    except (ValueError, TypeError):
        return None

    count_expr = (
        BehavioralEvent.query.with_entities(func.count(BehavioralEvent.id))
        .filter(
            BehavioralEvent.session_id == Session.id,
            BehavioralEvent.event_type == event_type,
        )
        .correlate(Session)
        .scalar_subquery()
    )

    if op == "eq":
        return count_expr == target
    if op == "neq":
        return count_expr != target
    if op == "gt":
        return count_expr > target
    if op == "gte":
        return count_expr >= target
    if op == "lt":
        return count_expr < target
    if op == "lte":
        return count_expr <= target
    return None


def _handle_behavior_count(query, event_type: str, op: str, value):
    cond = _build_behavior_count_condition(event_type, op, value)
    if cond is None:
        return query.filter(False)
    return query.filter(cond)


def _build_behavior_field_match(event_type: str, key: str | None, op: str, value):
    """Build EXISTS/NOT EXISTS condition for event field string matching."""
    from models import Session, BehavioralEvent

    if key:
        column = BehavioralEvent.data[key].astext
    else:
        column = BehavioralEvent.url

    base = BehavioralEvent.query.filter(
        BehavioralEvent.session_id == Session.id,
        BehavioralEvent.event_type == event_type,
        column != None,  # noqa: E711
        column != "",
    )

    if op in ("eq", "neq"):
        matched = base.filter(column == str(value))
        exists = matched.exists()
        return ~exists if op == "neq" else exists

    if op in ("contains", "not_contains"):
        matched = base.filter(column.ilike(f"%{value}%"))
        exists = matched.exists()
        return ~exists if op == "not_contains" else exists

    if op == "starts_with":
        return base.filter(column.ilike(f"{value}%")).exists()

    if op == "ends_with":
        return base.filter(column.ilike(f"%{value}")).exists()

    return None


def _handle_behavior_field(query, event_type: str, key: str | None, op: str, value):
    cond = _build_behavior_field_match(event_type, key, op, value)
    if cond is None:
        return query.filter(False)
    return query.filter(cond)


def _handle_behavior_button_click_count(query, op, value):
    return _handle_behavior_count(query, "button_click", op, value)


def _handle_behavior_form_submit_count(query, op, value):
    return _handle_behavior_count(query, "form_submit", op, value)


def _handle_behavior_copy_count(query, op, value):
    return _handle_behavior_count(query, "copy", op, value)


def _handle_behavior_paste_count(query, op, value):
    return _handle_behavior_count(query, "paste", op, value)


def _handle_behavior_button_text(query, op, value):
    return _handle_behavior_field(query, "button_click", "text", op, value)


def _handle_behavior_form_action(query, op, value):
    return _handle_behavior_field(query, "form_submit", "action", op, value)


def _handle_behavior_form_method(query, op, value):
    return _handle_behavior_field(query, "form_submit", "method", op, value)


def _handle_behavior_event_url(query, op, value):
    from models import Session, BehavioralEvent

    column = BehavioralEvent.url
    base = BehavioralEvent.query.filter(
        BehavioralEvent.session_id == Session.id,
        column != "",
    )

    if op in ("eq", "neq"):
        matched = base.filter(column == str(value))
        exists = matched.exists()
        return query.filter(~exists if op == "neq" else exists)

    if op in ("contains", "not_contains"):
        matched = base.filter(column.ilike(f"%{value}%"))
        exists = matched.exists()
        return query.filter(~exists if op == "not_contains" else exists)

    if op == "starts_with":
        return query.filter(base.filter(column.ilike(f"{value}%")).exists())

    if op == "ends_with":
        return query.filter(base.filter(column.ilike(f"%{value}")).exists())

    return query.filter(False)


def register_filters():
    """Register behavioral-event custom filters."""
    register_custom_filter(
        "behavior_button_click_count", "Behavior: Button Click Count", "number",
        _handle_behavior_button_click_count,
    )
    register_custom_filter(
        "behavior_form_submit_count", "Behavior: Form Submit Count", "number",
        _handle_behavior_form_submit_count,
    )
    register_custom_filter(
        "behavior_copy_count", "Behavior: Copy Count", "number",
        _handle_behavior_copy_count,
    )
    register_custom_filter(
        "behavior_paste_count", "Behavior: Paste Count", "number",
        _handle_behavior_paste_count,
    )
    register_custom_filter(
        "behavior_button_text", "Behavior: Button Text", "string",
        _handle_behavior_button_text,
        suggest=suggest_behavior_button_text,
    )
    register_custom_filter(
        "behavior_form_action", "Behavior: Form Action", "string",
        _handle_behavior_form_action,
        suggest=suggest_behavior_form_action,
    )
    register_custom_filter(
        "behavior_form_method", "Behavior: Form Method", "string",
        _handle_behavior_form_method,
        suggest=suggest_behavior_form_method,
    )
    register_custom_filter(
        "behavior_event_url", "Behavior: Event URL", "string",
        _handle_behavior_event_url,
        suggest=suggest_behavior_event_url,
    )
