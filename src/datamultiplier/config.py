"""Configuration structures for data generation."""

from dataclasses import dataclass, field
from typing import Any, Optional
import yaml


@dataclass
class ColumnConfig:
    """Configuration for a single database column."""

    name: str
    type: str
    nullable: bool = False
    unique: bool = False
    primary_key: bool = False
    auto_increment: bool = False
    foreign_key: Optional[str] = None  # "table.column" format
    faker_rule: Optional[str] = None  # faker method name or expression
    default_value: Optional[Any] = None


@dataclass
class TableConfig:
    """Configuration for a single table."""

    name: str
    row_count: int
    columns: list[ColumnConfig] = field(default_factory=list)

    def get_column(self, name: str) -> Optional[ColumnConfig]:
        """Get column config by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None


@dataclass
class GenerationConfig:
    """Top-level configuration for data generation."""

    seed: int = 42
    tables: list[TableConfig] = field(default_factory=list)

    def get_table(self, name: str) -> Optional[TableConfig]:
        """Get table config by name."""
        for table in self.tables:
            if table.name == name:
                return table
        return None

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "GenerationConfig":
        """Load configuration from YAML file."""
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        tables = []
        for table_name, table_data in data.get("tables", {}).items():
            columns = []
            for col_name, col_data in table_data.get("columns", {}).items():
                col = ColumnConfig(
                    name=col_name,
                    type=col_data.get("type"),
                    nullable=col_data.get("nullable", False),
                    unique=col_data.get("unique", False),
                    primary_key=col_data.get("primary_key", False),
                    auto_increment=col_data.get("auto_increment", False),
                    foreign_key=col_data.get("foreign_key"),
                    faker_rule=col_data.get("faker"),
                    default_value=col_data.get("default"),
                )
                columns.append(col)

            table = TableConfig(
                name=table_name,
                row_count=table_data.get("row_count", 10000),
                columns=columns,
            )
            tables.append(table)

        return cls(
            seed=data.get("seed", 42),
            tables=tables,
        )

    def to_yaml(self, yaml_path: str) -> None:
        """Save configuration to YAML file."""
        data = {
            "seed": self.seed,
            "tables": {},
        }

        for table in self.tables:
            columns = {}
            for col in table.columns:
                col_dict: dict[str, Any] = {"type": col.type}
                if col.nullable:
                    col_dict["nullable"] = True
                if col.unique:
                    col_dict["unique"] = True
                if col.primary_key:
                    col_dict["primary_key"] = True
                if col.auto_increment:
                    col_dict["auto_increment"] = True
                if col.foreign_key:
                    col_dict["foreign_key"] = col.foreign_key
                if col.faker_rule:
                    col_dict["faker"] = col.faker_rule
                if col.default_value is not None:
                    col_dict["default"] = col.default_value
                columns[col.name] = col_dict

            data["tables"][table.name] = {
                "row_count": table.row_count,
                "columns": columns,
            }

        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
