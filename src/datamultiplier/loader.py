"""Data loading utilities for importing CSV files into database."""

import csv
from pathlib import Path
from typing import Optional

from .db.connection import DatabaseConnection


class DataLoader:
    """Loads data from CSV files into database."""

    def __init__(self, db: DatabaseConnection):
        """Initialize loader with database connection."""
        self.db = db

    def load_file(self, file_path: str, table_name: Optional[str] = None) -> int:
        """Load a single CSV file into a table.

        Args:
            file_path: Path to CSV file
            table_name: Table name to load into (default: filename without .csv)

        Returns:
            Number of rows loaded

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If table doesn't exist or file format is invalid
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")

        # Infer table name from filename if not provided
        if table_name is None:
            if path.suffix.lower() != ".csv":
                raise ValueError(f"Expected .csv file, got: {path.name}")
            table_name = path.stem

        # Check table exists
        if not self.db.table_exists(table_name):
            raise ValueError(f"Table '{table_name}' does not exist")

        # Read CSV header to get column names
        with open(file_path, "r") as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                raise ValueError(f"CSV file is empty: {file_path}")

        if not headers:
            raise ValueError(f"CSV file has no headers: {file_path}")

        # Load using COPY with STDIN
        with self.db.get_cursor(commit=True) as cursor:
            with open(file_path, "r") as f:
                cursor.copy_expert(
                    f"COPY {table_name} ({', '.join(headers)}) FROM STDIN WITH (FORMAT csv, HEADER true)",
                    f,
                )
            row_count = cursor.rowcount

        return row_count

    def load_directory(self, dir_path: str, respect_fk_order: bool = False) -> dict:
        """Load all CSV files from a directory.

        Args:
            dir_path: Path to directory containing CSV files
            respect_fk_order: If True, load tables in FK dependency order
                             (parents before children). Falls back to
                             alphabetical order if dependencies can't be resolved.

        Returns:
            Dictionary mapping table names to row counts

        Raises:
            FileNotFoundError: If directory doesn't exist
        """
        dir_path_obj = Path(dir_path)
        if not dir_path_obj.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        csv_files = sorted(dir_path_obj.glob("*.csv"))
        if not csv_files:
            raise ValueError(f"No CSV files found in: {dir_path}")

        # Build table load order
        table_names = [f.stem for f in csv_files]

        if respect_fk_order:
            table_names = self._order_by_fk_dependencies(table_names)

        # Load files in order
        results = {}
        for table_name in table_names:
            file_path = dir_path_obj / f"{table_name}.csv"
            if file_path.exists():
                try:
                    row_count = self.load_file(str(file_path), table_name)
                    results[table_name] = row_count
                except Exception as e:
                    raise RuntimeError(f"Failed to load '{table_name}': {e}")

        return results

    def _order_by_fk_dependencies(self, table_names: list[str]) -> list[str]:
        """Order tables by FK dependencies (parents before children).

        If dependencies can't be resolved (cycles or missing tables),
        falls back to alphabetical order and logs a warning.

        Args:
            table_names: List of table names to order

        Returns:
            Ordered list of table names
        """
        # Build dependency graph
        dependencies = {}
        for table in table_names:
            fks = self.db.get_foreign_keys(table)
            deps = set()
            for fk in fks:
                parent_table = fk["foreign_table_name"]
                if parent_table in table_names:
                    deps.add(parent_table)
            dependencies[table] = deps

        # Topological sort with cycle detection
        ordered = []
        visited = set()
        visiting = set()

        def visit(table: str) -> bool:
            """Visit a table and its dependencies. Returns False if cycle detected."""
            if table in visited:
                return True
            if table in visiting:
                return False  # Cycle detected

            visiting.add(table)
            for dep in dependencies.get(table, set()):
                if not visit(dep):
                    return False
            visiting.remove(table)
            visited.add(table)
            ordered.append(table)
            return True

        # Try to sort all tables
        for table in table_names:
            if table not in visited:
                if not visit(table):
                    # Cycle detected, fall back to alphabetical
                    return sorted(table_names)

        return ordered
