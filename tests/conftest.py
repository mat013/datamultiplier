"""Pytest configuration and fixtures."""

import pytest
import os
import tempfile
from pathlib import Path


@pytest.fixture
def temp_config_file():
    """Create a temporary YAML config file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
seed: 42
tables:
  users:
    row_count: 100
    columns:
      id:
        type: integer
        primary_key: true
        auto_increment: true
      name:
        type: varchar
        faker: name
      email:
        type: varchar
        faker: email
        unique: true
  orders:
    row_count: 500
    columns:
      id:
        type: integer
        primary_key: true
        auto_increment: true
      user_id:
        type: integer
        foreign_key: users.id
      amount:
        type: numeric
        faker: "random_int(10, 9999)"
      created_at:
        type: timestamp
        faker: date_time
""")
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def db_url():
    """Get database URL from environment or use test database."""
    return os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost/datamultiplier_test")
