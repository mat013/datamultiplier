"""Tests for related-row extraction, using an in-memory row source."""

import pytest

from datamultiplier.extractor import FKRelation, RowExtractor, write_csv_dir


class MemorySource:
    def __init__(self, tables, columns, pks, relations):
        self.tables = tables
        self._columns = columns
        self._pks = pks
        self._relations = relations

    def relations(self):
        return self._relations

    def columns(self, table):
        return self._columns[table]

    def primary_key(self, table):
        return self._pks.get(table, [])

    def fetch(self, table, key_columns, keys):
        wanted = set(keys)
        return [
            dict(row)
            for row in self.tables[table]
            if tuple(row[c] for c in key_columns) in wanted
        ]


def _shop():
    tables = {
        "customers": [{"id": 1, "name": "Ann"}, {"id": 2, "name": "Bob"}],
        "products": [
            {"id": 10, "name": "pen"},
            {"id": 11, "name": "cup"},
            {"id": 12, "name": "bag"},
        ],
        "orders": [
            {"id": 100, "customer_id": 1},
            {"id": 101, "customer_id": 1},
            {"id": 102, "customer_id": 2},
        ],
        "order_items": [
            {"id": 1000, "order_id": 100, "product_id": 10},
            {"id": 1001, "order_id": 101, "product_id": 11},
            {"id": 1002, "order_id": 102, "product_id": 12},
        ],
    }
    columns = {
        "customers": ["id", "name"],
        "products": ["id", "name"],
        "orders": ["id", "customer_id"],
        "order_items": ["id", "order_id", "product_id"],
    }
    pks = {"customers": ["id"], "products": ["id"], "orders": ["id"], "order_items": ["id"]}
    relations = [
        FKRelation("orders", ("customer_id",), "customers", ("id",)),
        FKRelation("order_items", ("order_id",), "orders", ("id",)),
        FKRelation("order_items", ("product_id",), "products", ("id",)),
    ]
    return MemorySource(tables, columns, pks, relations)


def _ids(result, table):
    return sorted(r["id"] for r in result.rows.get(table, []))


def test_follows_parents_and_children_recursively_from_middle_row():
    result = RowExtractor(_shop(), max_rows=100).extract("orders", 100)

    assert _ids(result, "orders") == [100, 101]
    assert _ids(result, "customers") == [1]
    assert _ids(result, "order_items") == [1000, 1001]
    assert _ids(result, "products") == [10, 11]
    assert result.truncated is False


def test_does_not_pull_unrelated_rows():
    result = RowExtractor(_shop(), max_rows=100).extract("orders", 100)

    assert 2 not in _ids(result, "customers")
    assert 102 not in _ids(result, "orders")
    assert 12 not in _ids(result, "products")


def test_seed_from_leaf_walks_up_to_root():
    result = RowExtractor(_shop(), max_rows=100).extract("order_items", 1002)

    assert _ids(result, "order_items") == [1002]
    assert _ids(result, "orders") == [102]
    assert _ids(result, "customers") == [2]
    assert _ids(result, "products") == [12]


def test_null_foreign_key_is_ignored():
    source = _shop()
    source.tables["orders"].append({"id": 103, "customer_id": None})
    source.tables["order_items"].append({"id": 1003, "order_id": 103, "product_id": None})

    result = RowExtractor(source, max_rows=100).extract("orders", 103)

    assert _ids(result, "orders") == [103]
    assert "customers" not in result.rows
    assert "products" not in result.rows


def test_self_referencing_cycle_terminates():
    tables = {
        "employees": [
            {"id": 1, "manager_id": None},
            {"id": 2, "manager_id": 1},
            {"id": 3, "manager_id": 2},
            {"id": 4, "manager_id": 3},
        ]
    }
    source = MemorySource(
        tables,
        {"employees": ["id", "manager_id"]},
        {"employees": ["id"]},
        [FKRelation("employees", ("manager_id",), "employees", ("id",))],
    )

    result = RowExtractor(source, max_rows=100).extract("employees", 2)

    assert _ids(result, "employees") == [1, 2, 3, 4]


def test_composite_foreign_key_is_matched_on_all_columns():
    tables = {
        "parent": [{"a": 1, "b": 1}, {"a": 1, "b": 2}],
        "child": [{"id": 1, "pa": 1, "pb": 2}, {"id": 2, "pa": 2, "pb": 1}],
    }
    source = MemorySource(
        tables,
        {"parent": ["a", "b"], "child": ["id", "pa", "pb"]},
        {"parent": ["a", "b"], "child": ["id"]},
        [FKRelation("child", ("pa", "pb"), "parent", ("a", "b"))],
    )

    result = RowExtractor(source, max_rows=100).extract("child", 1, id_column="id")

    assert sorted((r["a"], r["b"]) for r in result.rows["parent"]) == [(1, 2)]


def test_max_rows_stops_and_marks_result_incomplete():
    result = RowExtractor(_shop(), max_rows=3).extract("orders", 100)

    assert result.truncated is True
    assert sum(len(rows) for rows in result.rows.values()) == 3


def test_unknown_seed_raises():
    with pytest.raises(ValueError):
        RowExtractor(_shop(), max_rows=100).extract("orders", 999)


def test_seed_without_single_primary_key_needs_id_column():
    source = _shop()
    source.primary_key = lambda table: []  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        RowExtractor(source, max_rows=100).extract("orders", 100)


def test_write_csv_dir_uses_dump_format(tmp_path):
    result = RowExtractor(_shop(), max_rows=100).extract("customers", 1)

    write_csv_dir(result, tmp_path / "out")

    text = (tmp_path / "out" / "customers.csv").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "id,name"
    assert "1,Ann" in text.splitlines()
