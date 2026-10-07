"""Heuristics for detecting personally-identifiable (PII) columns by name.

This is the single source of truth for "does this column name look like PII".
inspector.py uses it to pick a Faker rule; profiler.py uses it to decide which
columns must never have real sampled values stored.
"""
from typing import Optional


_PII_NAME_GROUPS: dict[str, tuple[str, ...]] = {
    "name": ("name", "full_name"),
    "first_name": ("first_name", "firstname"),
    "last_name": ("last_name", "lastname"),
    "email": ("email", "email_address"),
    "phone_number": ("phone", "phone_number"),
    "street_address": ("address", "street_address"),
    "city": ("city",),
    "country": ("country",),
    "zipcode": ("zip", "zipcode", "postal_code"),
    "user_name": ("username", "login"),
    "password": ("password",),
}

_PII_COLUMN_NAMES: frozenset[str] = frozenset(
    synonym for synonyms in _PII_NAME_GROUPS.values() for synonym in synonyms
)


def is_pii_like_column(column_name: str) -> bool:
    """Return True if a column name matches a known PII-like pattern."""
    return column_name.lower() in _PII_COLUMN_NAMES


def suggest_pii_faker_rule(column_name: str) -> Optional[str]:
    """Return the Faker rule name for a PII-like column, or None if not PII-like."""
    col_lower = column_name.lower()
    for faker_rule, synonyms in _PII_NAME_GROUPS.items():
        if col_lower in synonyms:
            return faker_rule
    return None
