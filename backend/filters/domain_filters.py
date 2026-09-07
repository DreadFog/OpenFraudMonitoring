from collections import Counter

from .registry import register_custom_filter


def _handle_domains(query, op, value):
    from models import Session

    domain = str(value or "").strip().lower()
    if not domain:
        return query.filter(False)

    matched = Session.domains.contains([domain])
    if op in {"eq", "contains"}:
        return query.filter(matched)
    if op == "neq":
        return query.filter(~matched)
    if op == "not_contains":
        return query.filter(~matched)
    return query.filter(False)


def _suggest_domains(query_value):
    from models import Session

    needle = (query_value or "").strip().lower()
    values = set()
    for (domains,) in Session.query.with_entities(Session.domains).yield_per(200):
        for domain in domains or []:
            if not needle or needle in domain.lower():
                values.add(domain)
                if len(values) >= 20:
                    return sorted(values)
    return sorted(values)


def _aggregate_domains(session_ids, limit):
    from models import Session

    counts = Counter()
    if not session_ids:
        return []
    rows = Session.query.with_entities(Session.domains).filter(Session.id.in_(session_ids)).all()
    for (domains,) in rows:
        for domain in set(domains or []):
            counts[domain] += 1
    return [
        {"value": domain, "count": count}
        for domain, count in counts.most_common(limit)
    ]


def register_filters():
    register_custom_filter(
        "domains",
        "Session Domains",
        "string",
        _handle_domains,
        suggest=_suggest_domains,
        aggregate=_aggregate_domains,
        category="Session Metadata",
    )
