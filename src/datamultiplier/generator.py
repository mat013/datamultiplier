"""Data generation engine."""

import random
from faker import Faker
from typing import Any, Optional
from decimal import Decimal

from .config import GenerationConfig, TableConfig, ColumnConfig
from .db.connection import DatabaseConnection


class DataGenerator:
    """Generates test data based on configuration."""

    def __init__(self, db: DatabaseConnection, config: GenerationConfig):
        """Initialize generator.

        Args:
            db: Database connection
            config: Generation configuration
        """
        self.db = db
        self.config = config
        self.fake = Faker()
        random.seed(config.seed)
        self.fake.seed_instance(config.seed)

        # Track generated IDs for foreign key relationships
        self.generated_ids: dict[str, list[Any]] = {}

    def generate_all(self) -> None:
        """Generate data for all tables in dependency order."""
        # Sort tables by foreign key dependencies
        ordered_tables = self._topological_sort()

        for table_config in ordered_tables:
            self.generate_table(table_config)

    def generate_table(self, table_config: TableConfig) -> None:
        """Generate and insert data for a single table."""
        print(f"Generating {table_config.row_count:,} rows for table '{table_config.name}'...")

        rows = []
        for _ in range(table_config.row_count):
            row = self._generate_row(table_config)
            rows.append(row)

        # Insert rows in batches
        column_names = [col.name for col in table_config.columns]
        self.db.batch_insert(table_config.name, column_names, rows)
        print(f"✓ Inserted {table_config.row_count:,} rows into '{table_config.name}'")

        # Store IDs for foreign key references
        self._store_ids(table_config)

    def _generate_row(self, table_config: TableConfig) -> tuple:
        """Generate a single row of data."""
        row = []

        for col in table_config.columns:
            value = self._generate_column_value(col)
            row.append(value)

        return tuple(row)

    def _generate_column_value(self, col: ColumnConfig) -> Any:
        """Generate a value for a single column."""
        # Skip auto-increment columns (let database handle it)
        if col.auto_increment:
            return None

        # Handle foreign keys
        if col.foreign_key:
            return self._generate_foreign_key_value(col.foreign_key)

        # Use faker rule if provided
        if col.faker_rule:
            return self._evaluate_faker_rule(col.faker_rule, col.type)

        # Default generation based on type
        return self._generate_by_type(col.type)

    def _generate_foreign_key_value(self, fk_reference: str) -> Any:
        """Generate a foreign key value by selecting from parent table."""
        table_name, _ = fk_reference.split(".")

        # Try to get from cached IDs
        if table_name in self.generated_ids:
            return random.choice(self.generated_ids[table_name])

        # Fallback: query database
        result = self.db.execute(f"SELECT id FROM {table_name} ORDER BY RANDOM() LIMIT 1")
        if result:
            return result[0]["id"]

        raise ValueError(f"No parent records found in table '{table_name}'")

    def _evaluate_faker_rule(self, rule: str, column_type: str) -> Any:
        """Evaluate a faker rule and return the generated value."""
        # Special handling for common patterns
        if rule == "name":
            return self.fake.name()
        if rule == "first_name":
            return self.fake.first_name()
        if rule == "last_name":
            return self.fake.last_name()
        if rule == "email":
            return self.fake.email()
        if rule == "phone_number":
            return self.fake.phone_number()
        if rule == "street_address":
            return self.fake.street_address()
        if rule == "city":
            return self.fake.city()
        if rule == "country":
            return self.fake.country()
        if rule == "zipcode":
            return self.fake.zipcode()
        if rule == "user_name":
            return self.fake.user_name()
        if rule == "password":
            return self.fake.password()
        if rule == "url":
            return self.fake.url()
        if rule == "date_time":
            return self.fake.date_time()
        if rule == "date":
            return self.fake.date()
        if rule == "time":
            return self.fake.time()
        if rule == "text":
            return self.fake.text(max_nb_chars=200)
        if rule == "boolean":
            return random.choice([True, False])
        if rule == "word":
            return self.fake.word()

        # Try to evaluate as Python expression
        # Safe subset: random_int, random_element, pydecimal
        try:
            if rule.startswith("random_int("):
                params = rule[11:-1]
                min_val, max_val = map(int, params.split(","))
                return random.randint(min_val, max_val)

            if rule.startswith("random_element("):
                import ast
                params = rule[15:-1]
                elements = ast.literal_eval(params)
                return random.choice(elements)

            if rule.startswith("pydecimal("):
                return self.fake.pydecimal(positive=True, min_value=0, max_value=999999, right_digits=2)

            # Try calling it as a faker method
            if hasattr(self.fake, rule):
                return getattr(self.fake, rule)()

        except Exception:
            pass

        # Fallback
        return self.fake.word()

    def _generate_by_type(self, column_type: str) -> Any:
        """Generate a value based on column type."""
        col_type_lower = column_type.lower()

        if col_type_lower.startswith("integer"):
            return random.randint(0, 999999)
        if col_type_lower.startswith("bigint"):
            return random.randint(0, 9999999999)
        if col_type_lower.startswith("numeric") or col_type_lower.startswith("decimal"):
            return Decimal(str(round(random.uniform(0, 99999.99), 2)))
        if col_type_lower.startswith("boolean"):
            return random.choice([True, False])
        if col_type_lower.startswith("timestamp"):
            return self.fake.date_time()
        if col_type_lower.startswith("date"):
            return self.fake.date()
        if col_type_lower.startswith("time"):
            return self.fake.time()
        if col_type_lower in ("character varying", "varchar", "text"):
            return self.fake.word()

        return None

    def _topological_sort(self) -> list[TableConfig]:
        """Sort tables by foreign key dependencies."""
        # Build dependency graph
        dependencies: dict[str, set[str]] = {}
        for table in self.config.tables:
            dependencies[table.name] = set()
            for col in table.columns:
                if col.foreign_key:
                    parent_table, _ = col.foreign_key.split(".")
                    dependencies[table.name].add(parent_table)

        # Kahn's algorithm for topological sort
        ordered = []
        in_degree = {t: len(dependencies[t]) for t in dependencies}

        queue = [t for t in dependencies if in_degree[t] == 0]
        while queue:
            current = queue.pop(0)
            ordered.append(self.config.get_table(current))

            # Find tables that depend on current
            for table_name, deps in dependencies.items():
                if current in deps:
                    deps.remove(current)
                    in_degree[table_name] -= 1
                    if in_degree[table_name] == 0:
                        queue.append(table_name)

        if len(ordered) != len(dependencies):
            raise ValueError("Circular dependency detected in table relationships")

        return [t for t in ordered if t is not None]

    def _store_ids(self, table_config: TableConfig) -> None:
        """Store generated IDs from a table for foreign key references."""
        pk_col = None
        for col in table_config.columns:
            if col.primary_key:
                pk_col = col.name
                break

        if pk_col:
            result = self.db.execute(f"SELECT {pk_col} FROM {table_config.name}")
            self.generated_ids[table_config.name] = [row[pk_col] for row in result]
