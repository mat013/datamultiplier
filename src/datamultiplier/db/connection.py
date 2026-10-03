"""Database connection management and utilities."""

import psycopg2
from psycopg2 import pool, extras
from contextlib import contextmanager
from typing import Optional, Generator


class DatabaseConnection:
    """Manages PostgreSQL connections and connection pooling."""

    def __init__(self, db_url: str, min_connections: int = 1, max_connections: int = 5, schema: str = "public"):
        """Initialize connection pool.

        Args:
            db_url: PostgreSQL connection URL (postgresql://user:pass@host/db)
            min_connections: Minimum pool size
            max_connections: Maximum pool size
            schema: Schema name to use (default: 'public')
        """
        self.db_url = db_url
        self.schema = schema
        self.pool: Optional[pool.SimpleConnectionPool] = None
        self.min_connections = min_connections
        self.max_connections = max_connections

    def connect(self) -> None:
        """Create connection pool."""
        if self.pool is None:
            self.pool = pool.SimpleConnectionPool(
                self.min_connections,
                self.max_connections,
                self.db_url,
            )

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
