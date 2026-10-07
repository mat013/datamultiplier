"""Database schema inspection and YAML configuration generation."""

from .config import GenerationConfig, TableConfig, ColumnConfig
from .db.connection import DatabaseConnection


class SchemaInspector:
    """Inspects PostgreSQL schema and generates configuration."""

    def __init__(self, db: DatabaseConnection):
        """Initialize inspector with database connection."""
        self.db = db

    def inspect_all_tables(self) -> GenerationConfig:
        """Inspect all tables in the database and return configuration."""
        config = GenerationConfig()

        table_names = self.db.get_all_tables()
        print(f"\nInspecting {len(table_names)} tables:")
        for i, table_name in enumerate(table_names, 1):
            print(f"  {i:2d}. {table_name}")
            table_config = self._inspect_table(table_name)
            config.tables.append(table_config)

        return config

    def _inspect_table(self, table_name: str) -> TableConfig:
        """Inspect a single table and return its configuration."""
        schema = self.db.get_table_schema(table_name)
        foreign_keys = self.db.get_foreign_keys(table_name)
        primary_key = self.db.get_primary_key(table_name)

        # Build foreign key lookup
        fk_map = {}
        for fk in foreign_keys:
            fk_map[fk["column_name"]] = f"{fk['foreign_table_name']}.{fk['foreign_column_name']}"

        columns = []
        for col in schema:
            col_config = ColumnConfig(
                name=col["column_name"],
                type=col["data_type"],
                nullable=col["is_nullable"] == "YES",
                primary_key=col["column_name"] == primary_key,
                auto_increment="nextval" in (col["column_default"] or ""),
                foreign_key=fk_map.get(col["column_name"]),
            )

            # Add faker rule suggestions based on column name
            if not col_config.primary_key:
                col_config.faker_rule = self._suggest_faker_rule(
                    col["column_name"],
                    col["data_type"],
                )

            columns.append(col_config)

        return TableConfig(
            name=table_name,
            row_count=10000,  # Default, user can customize
            columns=columns,
        )

    @staticmethod
    def _suggest_faker_rule(column_name: str, data_type: str) -> str:
        """Suggest a faker rule based on column name and type."""
        col_lower = column_name.lower()

        # Common name patterns
        if col_lower in ("name", "full_name"):
            return "name"
        if col_lower in ("first_name", "firstname"):
            return "first_name"
        if col_lower in ("last_name", "lastname"):
            return "last_name"
        if col_lower in ("email", "email_address"):
            return "email"
        if col_lower in ("phone", "phone_number"):
            return "phone_number"
        if col_lower in ("address", "street_address"):
            return "street_address"
        if col_lower in ("city",):
            return "city"
        if col_lower in ("country",):
            return "country"
        if col_lower in ("zip", "zipcode", "postal_code"):
            return "zipcode"
        if col_lower in ("username", "login"):
            return "user_name"
        if col_lower in ("password",):
            return "password"
        if col_lower in ("url", "website"):
            return "url"
        if col_lower in ("created_at", "created_date", "date_created"):
            return "date_time"
        if col_lower in ("updated_at", "modified_at", "date_modified"):
            return "date_time"
        if col_lower in ("started_at", "start_date"):
            return "date_time"
        if col_lower in ("ended_at", "end_date"):
            return "date_time"
        if col_lower in ("status",):
            return "random_element(['active', 'inactive', 'pending'])"

        # Type-based defaults
        if data_type.startswith("integer"):
            return "random_int(0, 999999)"
        if data_type.startswith("numeric") or data_type.startswith("decimal"):
            return "pydecimal(positive=True, min_value=0, max_value=999999, right_digits=2)"
        if data_type.startswith("boolean"):
            return "boolean"
        if data_type.startswith("timestamp"):
            return "date_time"
        if data_type.startswith("date"):
            return "date"
        if data_type.startswith("time"):
            return "time"
        if data_type.startswith("text") or data_type.startswith("character"):
            return "text"

        # Default fallback
        return "word"
