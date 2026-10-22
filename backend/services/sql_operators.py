"""Shared SQLAlchemy comparison operators for session and STIX filters."""


def apply_sql_operator(expression, op: str, value):
    """Apply a comparison operator to a SQLAlchemy expression."""
    if op == "eq":
        return expression == value
    if op == "neq":
        return expression != value
    if op == "contains":
        return expression.ilike(f"%{value}%")
    if op == "not_contains":
        return ~expression.ilike(f"%{value}%")
    if op == "starts_with":
        return expression.ilike(f"{value}%")
    if op == "ends_with":
        return expression.ilike(f"%{value}")
    if op == "gt":
        return expression > value
    if op == "gte":
        return expression >= value
    if op == "lt":
        return expression < value
    if op == "lte":
        return expression <= value
    return None
