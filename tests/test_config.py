"""Tests for configuration module."""

import tempfile
from pathlib import Path

from datamultiplier.config import GenerationConfig, TableConfig, ColumnConfig


def test_column_config_creation():
    """Test ColumnConfig creation."""
    col = ColumnConfig(
        name="id",
        type="integer",
        primary_key=True,
        auto_increment=True,
    )
    assert col.name == "id"
    assert col.type == "integer"
    assert col.primary_key is True
    assert col.auto_increment is True


def test_table_config_creation():
    """Test TableConfig creation."""
    col = ColumnConfig(name="id", type="integer", primary_key=True)
    table = TableConfig(name="users", row_count=1000, columns=[col])
    assert table.name == "users"
    assert table.row_count == 1000
    assert len(table.columns) == 1
    assert table.get_column("id") == col
    assert table.get_column("nonexistent") is None


def test_generation_config_from_yaml(temp_config_file):
    """Test loading configuration from YAML."""
    config = GenerationConfig.from_yaml(temp_config_file)
    assert config.seed == 42
    assert len(config.tables) == 2
    assert config.get_table("users") is not None
    assert config.get_table("orders") is not None

    users_table = config.get_table("users")
    assert users_table.row_count == 100
    assert len(users_table.columns) == 3


def test_generation_config_to_yaml(temp_config_file):
    """Test saving configuration to YAML."""
    # Load original
    config = GenerationConfig.from_yaml(temp_config_file)

    # Save to new file
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        output_path = f.name

    config.to_yaml(output_path)

    # Load saved file and compare
    config2 = GenerationConfig.from_yaml(output_path)
    assert config2.seed == config.seed
    assert len(config2.tables) == len(config.tables)

    # Cleanup
    Path(output_path).unlink()
