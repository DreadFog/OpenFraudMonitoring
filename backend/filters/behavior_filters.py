"""Session activity and behavioral-event custom filters and suggestions.

Behavior handlers query the typed event tables introduced to replace the
legacy JSONB behavioral_events table. Session activity handlers expose counts
for unique visited URLs and heartbeats.
"""

from sqlalchemy import func, cast
from sqlalchemy.dialects.postgresql import JSONB

from .registry import register_custom_filter
from .suggestions import (
    suggest_behavior_button_text,
    suggest_behavior_form_action,
    suggest_behavior_form_method,
    suggest_behavior_event_url,
    suggest_behavior_form_field_name,
    suggest_behavior_paste_target_name,
    suggest_behavior_copy_source_name,
)


# ─────────────────────────────────────────────────────────────────────────────
# Count helpers
# ─────────────────────────────────────────────────────────────────────────────

def _count_filter(Model, query, op, value):
    """Apply a count comparison on a model related to the current session."""
    return _count_models_filter((Model,), query, op, value)


def _count_models_filter(Models, query, op, value):
    """Apply a comparison to the combined row count of session-related models."""
    from models import Session

    try:
        target = int(float(value))
    except (ValueError, TypeError):
        return query.filter(False)

    count_expr = sum(
        (
            Model.query.with_entities(func.count(Model.id))
            .filter(Model.session_id == Session.id)
            .correlate(Session)
            .scalar_subquery()
        )
        for Model in Models
    )

    ops = {
        "eq":  count_expr == target,
        "neq": count_expr != target,
        "gt":  count_expr > target,
        "gte": count_expr >= target,
        "lt":  count_expr < target,
        "lte": count_expr <= target,
    }
    cond = ops.get(op)
    if cond is None:
        return query.filter(False)
    return query.filter(cond)


# ─────────────────────────────────────────────────────────────────────────────
# String column EXISTS helpers
# ─────────────────────────────────────────────────────────────────────────────

def _string_exists_filter(Model, column_name, query, op, value):
    """Apply an EXISTS condition matching a string column on a typed event model."""
    from models import Session

    column = getattr(Model, column_name)
    base = Model.query.filter(
        Model.session_id == Session.id,
        column != None,   # noqa: E711
        column != "",
    )

    if op == "eq":
        exists = base.filter(column == str(value)).exists()
    elif op == "neq":
        exists = ~base.filter(column == str(value)).exists()
    elif op == "contains":
        exists = base.filter(column.ilike(f"%{value}%")).exists()
    elif op == "not_contains":
        exists = ~base.filter(column.ilike(f"%{value}%")).exists()
    elif op == "starts_with":
        exists = base.filter(column.ilike(f"{value}%")).exists()
    elif op == "ends_with":
        exists = base.filter(column.ilike(f"%{value}")).exists()
    else:
        return query.filter(False)

    return query.filter(exists)


# ─────────────────────────────────────────────────────────────────────────────
# JSONB array (field_names) helpers
# ─────────────────────────────────────────────────────────────────────────────

def _form_field_name_filter(query, op, value):
    """Filter sessions that have a form_submit event whose field_names contains value."""
    from models import Session, FormSubmitEvent

    base = FormSubmitEvent.query.filter(
        FormSubmitEvent.session_id == Session.id,
    )

    if op in ("eq", "neq"):
        # PostgreSQL JSONB ? operator: checks whether array contains exact string
        matched = base.filter(
            FormSubmitEvent.field_names.cast(JSONB).op("?")(str(value))
        )
        exists = matched.exists()
        return query.filter(~exists if op == "neq" else exists)

    if op in ("contains", "not_contains", "starts_with", "ends_with"):
        # Unnest the JSONB array and apply string matching on each element
        from services.database import db
        from sqlalchemy import text as sa_text

        elem = func.jsonb_array_elements_text(FormSubmitEvent.field_names).column_valued("elem")
        if op == "contains":
            matched = base.filter(
                db.session.query(elem).filter(elem.ilike(f"%{value}%")).correlate(FormSubmitEvent).exists()
            )
        elif op == "not_contains":
            matched = base.filter(
                ~db.session.query(elem).filter(elem.ilike(f"%{value}%")).correlate(FormSubmitEvent).exists()
            )
        elif op == "starts_with":
            matched = base.filter(
                db.session.query(elem).filter(elem.ilike(f"{value}%")).correlate(FormSubmitEvent).exists()
            )
        elif op == "ends_with":
            matched = base.filter(
                db.session.query(elem).filter(elem.ilike(f"%{value}")).correlate(FormSubmitEvent).exists()
            )
        return query.filter(matched.exists())

    return query.filter(False)


# ─────────────────────────────────────────────────────────────────────────────
# Individual handlers (wired to registry below)
# ─────────────────────────────────────────────────────────────────────────────

def _handle_url_count(query, op, value):
    from models import SessionURL
    return _count_filter(SessionURL, query, op, value)


def _handle_heartbeat_count(query, op, value):
    from models import Heartbeat
    return _count_filter(Heartbeat, query, op, value)


def _handle_behavioral_event_count(query, op, value):
    from models.behavioral_event import TYPED_EVENT_MODELS
    return _count_models_filter(tuple(TYPED_EVENT_MODELS.values()), query, op, value)

def _handle_behavior_copy_count(query, op, value):
    from models import CopyEvent
    return _count_filter(CopyEvent, query, op, value)


def _handle_behavior_paste_count(query, op, value):
    from models import PasteEvent
    return _count_filter(PasteEvent, query, op, value)


def _handle_behavior_form_submit_count(query, op, value):
    from models import FormSubmitEvent
    return _count_filter(FormSubmitEvent, query, op, value)


def _handle_behavior_button_click_count(query, op, value):
    from models import ButtonClickEvent
    return _count_filter(ButtonClickEvent, query, op, value)


def _handle_behavior_button_text(query, op, value):
    from models import ButtonClickEvent
    return _string_exists_filter(ButtonClickEvent, "text", query, op, value)


def _handle_behavior_form_action(query, op, value):
    from models import FormSubmitEvent
    return _string_exists_filter(FormSubmitEvent, "action", query, op, value)


def _handle_behavior_form_method(query, op, value):
    from models import FormSubmitEvent
    return _string_exists_filter(FormSubmitEvent, "method", query, op, value)


def _handle_behavior_event_url(query, op, value):
    """Match the url column across all typed event tables (any event type)."""
    from models import Session, CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent

    def _url_exists(Model, op, value):
        base = Model.query.filter(
            Model.session_id == Session.id,
            Model.url != "",
        )
        if op == "eq":
            return base.filter(Model.url == str(value)).exists()
        if op == "neq":
            return ~base.filter(Model.url == str(value)).exists()
        if op == "contains":
            return base.filter(Model.url.ilike(f"%{value}%")).exists()
        if op == "not_contains":
            return ~base.filter(Model.url.ilike(f"%{value}%")).exists()
        if op == "starts_with":
            return base.filter(Model.url.ilike(f"{value}%")).exists()
        if op == "ends_with":
            return base.filter(Model.url.ilike(f"%{value}")).exists()
        return None

    from sqlalchemy import or_
    conds = [c for m in (CopyEvent, PasteEvent, FormSubmitEvent, ButtonClickEvent)
             if (c := _url_exists(m, op, value)) is not None]
    if not conds:
        return query.filter(False)
    return query.filter(or_(*conds))


def _handle_behavior_form_field_name(query, op, value):
    return _form_field_name_filter(query, op, value)


def _handle_behavior_paste_target_name(query, op, value):
    from models import PasteEvent
    return _string_exists_filter(PasteEvent, "target_name", query, op, value)


def _handle_behavior_paste_target_id(query, op, value):
    from models import PasteEvent
    return _string_exists_filter(PasteEvent, "target_id", query, op, value)


def _handle_behavior_copy_source_name(query, op, value):
    from models import CopyEvent
    return _string_exists_filter(CopyEvent, "source_name", query, op, value)


def _handle_behavior_copy_source_id(query, op, value):
    from models import CopyEvent
    return _string_exists_filter(CopyEvent, "source_id", query, op, value)


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

def register_filters():
    """Register session activity and behavioral-event custom filters."""
    register_custom_filter(
        "url_count", "Visited URL Count", "number",
        _handle_url_count,
        category="Session Metadata",
    )
    register_custom_filter(
        "heartbeat_count", "Heartbeat Count", "number",
        _handle_heartbeat_count,
        category="Session Metadata",
    )
    register_custom_filter(
        "behavioral_event_count", "Behavioral Event Count", "number",
        _handle_behavioral_event_count,
        category="Behavior",
    )
    # Counts
    register_custom_filter(
        "behavior_button_click_count", "Behavior: Button Click Count", "number",
        _handle_behavior_button_click_count,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_form_submit_count", "Behavior: Form Submit Count", "number",
        _handle_behavior_form_submit_count,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_copy_count", "Behavior: Copy Count", "number",
        _handle_behavior_copy_count,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_paste_count", "Behavior: Paste Count", "number",
        _handle_behavior_paste_count,
        category="Behavior",
    )
    # Form fields
    register_custom_filter(
        "behavior_button_text", "Behavior: Button Text", "string",
        _handle_behavior_button_text,
        suggest=suggest_behavior_button_text,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_form_action", "Behavior: Form Action", "string",
        _handle_behavior_form_action,
        suggest=suggest_behavior_form_action,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_form_method", "Behavior: Form Method", "string",
        _handle_behavior_form_method,
        suggest=suggest_behavior_form_method,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_event_url", "Behavior: Event URL", "string",
        _handle_behavior_event_url,
        suggest=suggest_behavior_event_url,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_form_field_name", "Behavior: Form Field Name", "string",
        _handle_behavior_form_field_name,
        suggest=suggest_behavior_form_field_name,
        category="Behavior",
    )
    # Paste target context
    register_custom_filter(
        "behavior_paste_target_name", "Behavior: Paste Target Name", "string",
        _handle_behavior_paste_target_name,
        suggest=suggest_behavior_paste_target_name,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_paste_target_id", "Behavior: Paste Target ID", "string",
        _handle_behavior_paste_target_id,
        category="Behavior",
    )
    # Copy source context
    register_custom_filter(
        "behavior_copy_source_name", "Behavior: Copy Source Name", "string",
        _handle_behavior_copy_source_name,
        suggest=suggest_behavior_copy_source_name,
        category="Behavior",
    )
    register_custom_filter(
        "behavior_copy_source_id", "Behavior: Copy Source ID", "string",
        _handle_behavior_copy_source_id,
        category="Behavior",
    )

