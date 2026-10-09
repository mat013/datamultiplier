"""Database connection management and utilities."""

import psycopg2
from psycopg2 import pool, extras
from contextlib import contextmanager
from typing import Optional, Generator


class DatabaseConnection:
    """Manages PostgreSQL connections and connection pooling."""

    def __init__(self, db_url: str, min_connections: int = 1, max_connections: int = 5, schema: Optional[str] = None):
        """Initialize connection pool.

        Args:
            db_url: PostgreSQL connection URL (postgresql://user:pass@host/db)
            min_connections: Minimum pool size
            max_connections: Maximum pool size
            schema: Schema name to use (None = use user's default search_path)
        """
        self.db_url = db_url
        self._requested_schema = schema
        self._schema: Optional[str] = None
        self.pool: Optional[pool.SimpleConnectionPool] = None
        self.min_connections = min_connections
        self.max_connections = max_connections

    @property
    def schema(self) -> str:
        """Get the effective schema name."""
        if self._schema is None:
            raise RuntimeError("Schema not determined yet. Call connect() first.")
        return self._schema

    def connect(self) -> None:
        """Create connection pool and determine schema."""
        if self.pool is None:
            self.pool = pool.SimpleConnectionPool(
                self.min_connections,
                self.max_connections,
                self.db_url,
            )

        # Determine the effective schema on first connection
        if self._schema is None:
            if self._requested_schema:
                self._schema = self._requested_schema
            else:
                # Use the user's default schema from search_path
                with self.get_cursor() as cursor:
                    cursor.execute("SELECT current_schema()")
                    result = cursor.fetchone()
                    self._schema = result["current_schema"] if result and result["current_schema"] else "public"

    def disconnect(self) -> None:
        """Close all connections in pool."""
        if self.pool:
            self.pool.closeall()
            self.pool = None

    @contextmanager
    def get_connection(self) -> Generator:
        """Get a connection from the pool."""
        if self.pool is None:
            self.connect()

        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    @contextmanager
    def get_cursor(self, commit: bool = False) -> Generator:
        """Get a cursor for executing queries.

        Args:
            commit: Automatically commit after context exit
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
            try:
                yield cursor
                if commit:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

    def execute(self, query: str, params: tuple = ()) -> list[dict]:
        """Execute a SELECT query and return results."""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute_write(self, query: str, params: tuple = ()) -> int:
        """Execute a write query (INSERT/UPDATE/DELETE) and return affected rows."""
        with self.get_cursor(commit=True) as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def batch_insert(self, table: str, columns: list[str], rows: list[tuple]) -> int:
        """Bulk insert rows using COPY for performance.

        Args:
            table: Table name
            columns: List of column names
            rows: List of row tuples

        Returns:
            Number of rows inserted
        """
        with self.get_cursor(commit=True) as cursor:
            # Use executemany for smaller batches or COPY for very large batches
            if len(rows) < 10000:
                query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
                extras.executemany(cursor, query, rows, page_size=1000)
            else:
                # Use COPY for large batches - much faster
                import io
                buffer = io.StringIO()
                for row in rows:
                    buffer.write("\t".join(str(v) if v is not None else "\\N" for v in row))
                    buffer.write("\n")
                buffer.seek(0)

                cursor.copy_from(
                    buffer,
                    table,
                    columns=columns,
                    null="\\N",
                )

            return cursor.rowcount

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        query = """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = %s
            )
        """
        result = self.execute(query, (table_name,))
        return result[0]["exists"] if result else False

    def get_table_schema(self, table_name: str) -> list[dict]:
        """Get column information for a table."""
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        return self.execute(query, (self.schema, table_name))

    def get_foreign_keys(self, table_name: str) -> list[dict]:
        """Get foreign key constraints for a table."""
        query = """
            SELECT
                rc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.referential_constraints rc
            JOIN information_schema.key_column_usage kcu
                ON rc.constraint_name = kcu.constraint_name
                AND kcu.table_schema = %s
            JOIN information_schema.constraint_column_usage ccu
                ON rc.unique_constraint_name = ccu.constraint_name
            WHERE kcu.table_name = %s
        """
        return self.execute(query, (self.schema, table_name))

    def get_primary_key(self, table_name: str) -> Optional[str]:
        """Get the primary key column name for a table."""
        query = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_schema = %s
                AND tc.table_name = %s
                AND tc.constraint_type = 'PRIMARY KEY'
            LIMIT 1
        """
        result = self.execute(query, (self.schema, table_name))
        return result[0]["column_name"] if result else None

    def get_all_tables(self) -> list[str]:
        """Get list of all table names in the database."""
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
        """
        result = self.execute(query, (self.schema,))
        return [row["table_name"] for row in result]

    def get_fk_definitions(self) -> list[dict]:
        """Get all foreign key definitions in the schema.

        Returns list of dicts with: constraint_name, table_name, definition
        """
        query = """
            SELECT
                c.conname AS constraint_name,
                t.relname AS table_name,
                pg_get_constraintdef(c.oid) AS definition
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = %s
                AND c.contype = 'f'
            ORDER BY t.relname, c.conname
        """
        result = self.execute(query, (self.schema,))
        return result

    def drop_fk(self, table_name: str, constraint_name: str) -> None:
        """Drop a foreign key constraint."""
        query = f"ALTER TABLE {self.schema}.{table_name} DROP CONSTRAINT {constraint_name}"
        self.execute_write(query)

    def add_fk(self, table_name: str, constraint_name: str, definition: str, not_valid: bool = False) -> None:
        """Add a foreign key constraint.

        Args:
            table_name: Table name
            constraint_name: Constraint name
            definition: Complete definition from pg_get_constraintdef (includes FOREIGN KEY ... part)
            not_valid: If True, add constraint as NOT VALID (skips validation, faster for large tables)
        """
        query = f"ALTER TABLE {self.schema}.{table_name} ADD CONSTRAINT {constraint_name} {definition}"
        if not_valid:
            query += " NOT VALID"
        self.execute_write(query)

        if not_valid:
            validate_query = f"ALTER TABLE {self.schema}.{table_name} VALIDATE CONSTRAINT {constraint_name}"
            self.execute_write(validate_query)
