"""Tests for SchemaInspector's Faker rule suggestions."""

import pytest
from datamultiplier.inspector import SchemaInspector


def test_suggest_faker_rule_pii_names() -> None:
    """Test that PII-like column names get correct Faker rule suggestions."""
    assert SchemaInspector._suggest_faker_rule("name", "varchar") == "name"
    assert SchemaInspector._suggest_faker_rule("full_name", "varchar") == "name"
    assert SchemaInspector._suggest_faker_rule("first_name", "varchar") == "first_name"
    assert SchemaInspector._suggest_faker_rule("firstname", "varchar") == "first_name"
    assert SchemaInspector._suggest_faker_rule("last_name", "varchar") == "last_name"
    assert SchemaInspector._suggest_faker_rule("lastname", "varchar") == "last_name"


def test_suggest_faker_rule_pii_contact() -> None:
    """Test contact-related PII columns."""
    assert SchemaInspector._suggest_faker_rule("email", "varchar") == "email"
    assert SchemaInspector._suggest_faker_rule("email_address", "varchar") == "email"
    assert SchemaInspector._suggest_faker_rule("phone", "varchar") == "phone_number"
    assert SchemaInspector._suggest_faker_rule("phone_number", "varchar") == "phone_number"
    assert SchemaInspector._suggest_faker_rule("address", "varchar") == "street_address"
    assert SchemaInspector._suggest_faker_rule("street_address", "varchar") == "street_address"
    assert SchemaInspector._suggest_faker_rule("city", "varchar") == "city"
    assert SchemaInspector._suggest_faker_rule("country", "varchar") == "country"
    assert SchemaInspector._suggest_faker_rule("zip", "varchar") == "zipcode"
    assert SchemaInspector._suggest_faker_rule("zipcode", "varchar") == "zipcode"
    assert SchemaInspector._suggest_faker_rule("postal_code", "varchar") == "zipcode"


def test_suggest_faker_rule_pii_credentials() -> None:
    """Test credential-related PII columns."""
    assert SchemaInspector._suggest_faker_rule("username", "varchar") == "user_name"
    assert SchemaInspector._suggest_faker_rule("login", "varchar") == "user_name"
    assert SchemaInspector._suggest_faker_rule("password", "varchar") == "password"


def test_suggest_faker_rule_non_pii_urls() -> None:
    """Test that URL columns get url rule (not PII-like)."""
    assert SchemaInspector._suggest_faker_rule("url", "varchar") == "url"
    assert SchemaInspector._suggest_faker_rule("website", "varchar") == "url"


def test_suggest_faker_rule_temporal() -> None:
    """Test that temporal columns get date_time rules."""
    assert SchemaInspector._suggest_faker_rule("created_at", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("created_date", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("date_created", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("updated_at", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("modified_at", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("date_modified", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("started_at", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("start_date", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("ended_at", "timestamp") == "date_time"
    assert SchemaInspector._suggest_faker_rule("end_date", "timestamp") == "date_time"


def test_suggest_faker_rule_status() -> None:
    """Test that status column gets the status rule."""
    assert SchemaInspector._suggest_faker_rule("status", "varchar") == "random_element(['active', 'inactive', 'pending'])"


def test_suggest_faker_rule_case_insensitive() -> None:
    """Test that column name matching is case-insensitive."""
    assert SchemaInspector._suggest_faker_rule("EMAIL", "varchar") == "email"
    assert SchemaInspector._suggest_faker_rule("Email", "varchar") == "email"
    assert SchemaInspector._suggest_faker_rule("CREATED_AT", "timestamp") == "date_time"


def test_suggest_faker_rule_type_based_fallback() -> None:
    """Test type-based default rules when column name doesn't match any pattern."""
    assert SchemaInspector._suggest_faker_rule("age", "integer") == "random_int(0, 999999)"
    assert SchemaInspector._suggest_faker_rule("amount", "numeric") == "pydecimal(positive=True, min_value=0, max_value=999999, right_digits=2)"
    assert SchemaInspector._suggest_faker_rule("active", "boolean") == "boolean"
    assert SchemaInspector._suggest_faker_rule("published_date", "date") == "date"
    assert SchemaInspector._suggest_faker_rule("published_time", "time") == "time"
    assert SchemaInspector._suggest_faker_rule("bio", "text") == "text"
