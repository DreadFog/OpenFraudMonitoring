"""Registry for custom session filters."""

# Each entry: {"name", "label", "type", "handler", "suggest", "aggregate"}
_CUSTOM_FILTERS: dict[str, dict] = {}


def register_custom_filter(name: str, label: str, field_type: str, handler,
                           suggest=None, aggregate=None):
    """Register or replace a custom filter definition."""
    _CUSTOM_FILTERS[name] = {
        "name": name,
        "label": label,
        "type": field_type,
        "handler": handler,
        "suggest": suggest,
        "aggregate": aggregate,
    }


def get_custom_handler(field_name: str):
    """Return a custom filter handler or None."""
    entry = _CUSTOM_FILTERS.get(field_name)
    return entry["handler"] if entry else None


def get_custom_fields() -> list[dict]:
    """Return schema metadata for all registered custom filters."""
    return [
        {"name": f["name"], "label": f["label"], "type": f["type"]}
        for f in _CUSTOM_FILTERS.values()
    ]


def get_custom_suggestions(field_name: str, q: str) -> list[str] | None:
    """Return suggestions for a custom field or None if unsupported."""
    entry = _CUSTOM_FILTERS.get(field_name)
    if not entry or entry["suggest"] is None:
        return None
    return entry["suggest"](q)


def get_custom_aggregate(field_name: str, session_ids, limit: int):
    """Return aggregate buckets for a custom field or None if unsupported."""
    entry = _CUSTOM_FILTERS.get(field_name)
    if not entry or entry["aggregate"] is None:
        return None
    return entry["aggregate"](session_ids, limit)
