"""
Schema service — re-exports from the central schema registry.

The schema registry (schema_registry.py) is the single source of truth.
This module exists for backward compatibility with imports from services.schema.
"""

from schema_registry import OPERATORS, SCHEMA_FIELDS, get_schema, get_field_meta

__all__ = ["OPERATORS", "SCHEMA_FIELDS", "get_schema", "get_field_meta"]
