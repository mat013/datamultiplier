"""Data export/dump utilities."""

import csv
from typing import Optional

from .db.connection import DatabaseConnection


class DataDumper:
    """Exports database data to various formats."""

    def __init__(self, db: DatabaseConnection):
        """Initialize dumper with database connection."""
        self.db = db

    def dump_table_to_csv(
        self,
        table_name: str,
        output_path: str,
        where_clause: Optional[str] = None,
    ) -> int:
        """Export table data to CSV file.

        Args:
            table_name: Name of table to export
            output_path: Path to output CSV file
            where_clause: Optional WHERE clause to filter rows

        Returns:
            Number of rows exported
        """
        query = f"SELECT * FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"

        with self.db.get_cursor() as cursor:
            cursor.execute(query)

            # Get column names from cursor description
            if cursor.description is None:
                raise ValueError(f"Table '{table_name}' not found or is empty")

            column_names = [desc[0] for desc in cursor.description]

            # Stream to CSV file
            row_count = 0
            with open(output_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(column_names)

                for row in cursor.fetchall():
                    writer.writerow([row.get(col) for col in column_names])
                    row_count += 1

        print(f"✓ Exported {row_count:,} rows from '{table_name}' to '{output_path}'")
        return row_count

    def dump_all_tables_to_csv(self, output_dir: str) -> None:
        """Export all tables to separate CSV files.

        Args:
            output_dir: Directory to write CSV files to
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        tables = self.db.get_all_tables()
        for table_name in tables:
            output_path = os.path.join(output_dir, f"{table_name}.csv")
            self.dump_table_to_csv(table_name, output_path)

        print(f"✓ Exported {len(tables)} tables to '{output_dir}'")

    def dump_table_to_sql(
        self,
        table_name: str,
        output_path: str,
        where_clause: Optional[str] = None,
    ) -> int:
        """Export table data as SQL INSERT statements.

        Args:
            table_name: Name of table to export
            output_path: Path to output SQL file
            where_clause: Optional WHERE clause to filter rows

        Returns:
            Number of rows exported
        """
        query = f"SELECT * FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"

        with self.db.get_cursor() as cursor:
            cursor.execute(query)

            if cursor.description is None:
                raise ValueError(f"Table '{table_name}' not found or is empty")

            column_names = [desc[0] for desc in cursor.description]

            row_count = 0
            with open(output_path, "w") as f:
                for row in cursor.fetchall():
                    values = []
                    for col in column_names:
                        val = row.get(col)
                        if val is None:
                            values.append("NULL")
                        elif isinstance(val, str):
                            values.append(f"'{val.replace(chr(39), chr(39)*2)}'")
                        elif isinstance(val, bool):
                            values.append("TRUE" if val else "FALSE")
                        else:
                            values.append(str(val))

                    insert_stmt = f"INSERT INTO {table_name} ({', '.join(column_names)}) VALUES ({', '.join(values)});\n"
                    f.write(insert_stmt)
                    row_count += 1

        print(f"✓ Exported {row_count:,} rows from '{table_name}' to '{output_path}'")
        return row_count
