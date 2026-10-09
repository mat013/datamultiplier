"""Extract the rows related to one seed row by following foreign keys in both directions."""

import csv
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Protocol

from psycopg2 import extras, sql

from .db.connection import DatabaseConnection

FETCH_BATCH_SIZE = 1000

Row = dict[str, Any]
Progress = Callable[[str, int, int], None]


@dataclass(frozen=True)
class FKRelation:
    child_table: str
    child_columns: tuple[str, ...]
    parent_table: str
    parent_columns: tuple[str, ...]


class RowSource(Protocol):
    def relations(self) -> list[FKRelation]: ...

    def columns(self, table: str) -> list[str]: ...

    def primary_key(self, table: str) -> list[str]: ...

    def fetch(self, table: str, key_columns: tuple[str, ...], keys: list[tuple]) -> list[Row]: ...


@dataclass
class ExtractResult:
    columns: dict[str, list[str]]
    rows: dict[str, list[Row]]
    truncated: bool


class RowExtractor:
    """Breadth-first walk over foreign keys, starting from one row."""

    def __init__(self, source: RowSource, max_rows: int, progress: Optional[Progress] = None):
        self.source = source
        self.max_rows = max_rows
        self.progress = progress
        self._columns: dict[str, list[str]] = {}
        self._identity: dict[str, tuple[str, ...]] = {}
        self._parents_of: dict[str, list[FKRelation]] = defaultdict(list)
        self._children_of: dict[str, list[FKRelation]] = defaultdict(list)
        self._found: dict[str, dict[tuple, Row]] = defaultdict(dict)
        self._total = 0
        self._truncated = False

    def extract(self, table: str, id_value: Any, id_column: Optional[str] = None) -> ExtractResult:
        for rel in self.source.relations():
            self._parents_of[rel.child_table].append(rel)
            self._children_of[rel.parent_table].append(rel)

        if id_column is None:
            pk = self.source.primary_key(table)
            if len(pk) != 1:
                raise ValueError(f"'{table}' har ingen enkelt primærnøgle; angiv id-kolonne")
            id_column = pk[0]

        seed = self.source.fetch(table, (id_column,), [(id_value,)])
        if not seed:
            raise ValueError(f"Ingen række i '{table}' med {id_column} = {id_value}")

        frontier: dict[str, list[Row]] = defaultdict(list)
        for row in seed:
            if self._add(table, row):
                frontier[table].append(row)

        while frontier and not self._truncated:
            next_frontier: dict[str, list[Row]] = defaultdict(list)
            for current, rows in frontier.items():
                for rel in self._parents_of[current]:
                    keys = _keys(rows, rel.child_columns)
                    if keys:
                        self._absorb(rel.parent_table, rel.parent_columns, keys, next_frontier)
                for rel in self._children_of[current]:
                    keys = _keys(rows, rel.parent_columns)
                    if keys:
                        self._absorb(rel.child_table, rel.child_columns, keys, next_frontier)
                if self._truncated:
                    break
            frontier = next_frontier

        rows_out: dict[str, list[Row]] = {}
        columns_out: dict[str, list[str]] = {}
        for tbl, found in self._found.items():
            if not found:
                continue
            ident = self._identity_of(tbl)
            rows_out[tbl] = sorted(found.values(), key=lambda r: tuple(str(r[c]) for c in ident))
            columns_out[tbl] = self._cols(tbl)
        return ExtractResult(columns=columns_out, rows=rows_out, truncated=self._truncated)

    def _absorb(
        self,
        table: str,
        key_columns: tuple[str, ...],
        keys: list[tuple],
        next_frontier: dict[str, list[Row]],
    ) -> None:
        added = 0
        for start in range(0, len(keys), FETCH_BATCH_SIZE):
            for row in self.source.fetch(table, key_columns, keys[start:start + FETCH_BATCH_SIZE]):
                if self._add(table, row):
                    next_frontier[table].append(row)
                    added += 1
                if self._truncated:
                    break
            if self._truncated:
                break
        if added and self.progress:
            self.progress(table, added, self._total)

    def _add(self, table: str, row: Row) -> bool:
        identity = tuple(row[c] for c in self._identity_of(table))
        if identity in self._found[table]:
            return False
        if self._total >= self.max_rows:
            self._truncated = True
            return False
        self._found[table][identity] = row
        self._total += 1
        return True

    def _cols(self, table: str) -> list[str]:
        if table not in self._columns:
            self._columns[table] = self.source.columns(table)
        return self._columns[table]

    def _identity_of(self, table: str) -> tuple[str, ...]:
        if table not in self._identity:
            pk = self.source.primary_key(table)
            self._identity[table] = tuple(pk) if pk else tuple(self._cols(table))
        return self._identity[table]


def _keys(rows: list[Row], columns: tuple[str, ...]) -> list[tuple]:
    keys = {tuple(r[c] for c in columns) for r in rows}
    return [k for k in keys if all(v is not None for v in k)]


class PostgresSource:
    """Reads from one schema inside a single read-only, repeatable-read transaction."""

    def __init__(self, db: DatabaseConnection):
        self.db = db
        self._conn = None

    @contextmanager
    def snapshot(self) -> Iterator["PostgresSource"]:
        with self.db.get_connection() as conn:
            conn.rollback()
            conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
            self._conn = conn
            try:
                yield self
            finally:
                conn.rollback()
                self._conn = None

    def relations(self) -> list[FKRelation]:
        return [
            FKRelation(
                child_table=r["child_table"],
                child_columns=tuple(r["child_columns"]),
                parent_table=r["parent_table"],
                parent_columns=tuple(r["parent_columns"]),
            )
            for r in self.db.get_fk_relations()
        ]

    def columns(self, table: str) -> list[str]:
        return [r["column_name"] for r in self.db.get_table_schema(table)]

    def primary_key(self, table: str) -> list[str]:
        return self.db.get_primary_key_columns(table)

    def fetch(self, table: str, key_columns: tuple[str, ...], keys: list[tuple]) -> list[Row]:
        if self._conn is None:
            raise RuntimeError("PostgresSource.fetch must be called inside snapshot()")

        key_list = sql.SQL(", ").join(sql.Identifier(c) for c in key_columns)
        one_key = sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() for _ in key_columns))
        in_list = sql.SQL(", ").join(one_key for _ in keys)
        query = sql.SQL("SELECT * FROM {}.{} WHERE ({}) IN ({})").format(
            sql.Identifier(self.db.schema),
            sql.Identifier(table),
            key_list,
            in_list,
        )
        params = [v for key in keys for v in key]

        with self._conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]


def write_csv_dir(result: ExtractResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, rows in result.rows.items():
        columns = result.columns[table]
        with open(out_dir / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([row[c] for c in columns])
