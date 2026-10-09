"""Tests for CSV column statistics."""

import json
import random

import pytest

from datamultiplier.config import ColumnConfig, TableConfig
from datamultiplier.sampler import (
    ColumnAccumulator,
    SampleOptions,
    TableSampler,
    compute_relations,
    write_stat,
)


def _accumulate(values, declared=None, options=None, skip_reason=None):
    acc = ColumnAccumulator(
        "col",
        declared,
        options or SampleOptions(),
        random.Random(1),
        skip_reason=skip_reason,
    )
    for v in values:
        acc.add(v)
    return acc.result()


def test_number_range_and_full_distribution_when_few_distinct():
    values = ["10", "10", "250", "9999", "10", "250"]
    result = _accumulate(values, options=SampleOptions(max_distinct=5, top=1))

    assert result["kind"] == "number"
    assert result["from"] == 10
    assert result["to"] == 9999
    assert result["nulls"] == 0
    assert result["top"] == {"10": 3, "250": 2, "9999": 1}


def test_number_with_many_distinct_values_keeps_top_n_only():
    values = ["10", "10", "250", "9999", "10", "250"]
    result = _accumulate(values, options=SampleOptions(max_distinct=2, top=1))

    assert result["top"] == {"10": 3}
    assert result["from"] == 10
    assert result["to"] == 9999


def test_number_with_many_distinct_keeps_only_top_n():
    values = [str(i) for i in range(50)] + ["7"] * 10
    result = _accumulate(values, options=SampleOptions(max_distinct=5, top=2))

    assert result["kind"] == "number"
    assert result["top"]["7"] == 11
    assert len(result["top"]) == 2


def test_decimal_range():
    result = _accumulate(["1.5", "2.25", "0.5"])

    assert result["kind"] == "number"
    assert result["from"] == 0.5
    assert result["to"] == 2.25


def test_temporal_range_from_timestamps():
    values = ["2024-03-01 10:00:00", "2023-01-15 08:30:00", "2024-02-29 12:00:00"]
    result = _accumulate(values)

    assert result["kind"] == "temporal"
    assert result["from"] == "2023-01-15T08:30:00"
    assert result["to"] == "2024-03-01T10:00:00"


def test_short_text_with_few_distinct_values_is_enum():
    values = ["NEW", "NEW", "DONE", "NEW", "OPEN"]
    result = _accumulate(values)

    assert result["kind"] == "enum"
    assert result["counts"] == {"NEW": 3, "DONE": 1, "OPEN": 1}


def test_text_longer_than_limit_becomes_samples():
    long_text = "x" * 80
    result = _accumulate([long_text, "a", "a"], options=SampleOptions(max_text_length=70))

    assert result["kind"] == "text"
    assert long_text in result["samples"]


def test_text_samples_are_bounded_by_max_samples():
    values = [f"name-{i}" for i in range(500)]
    result = _accumulate(values, options=SampleOptions(max_samples=5, max_distinct=3))

    assert result["kind"] == "text"
    assert len(result["samples"]) == 5


def test_max_text_length_is_configurable():
    values = ["abcdef", "abcdef"]
    short = _accumulate(values, options=SampleOptions(max_text_length=70))
    long = _accumulate(values, options=SampleOptions(max_text_length=3))

    assert short["kind"] == "enum"
    assert long["kind"] == "text"


def test_empty_cells_count_as_nulls():
    result = _accumulate(["1", "", "2", ""])

    assert result["kind"] == "number"
    assert result["nulls"] == 2


def test_column_with_only_empty_cells_is_empty():
    assert _accumulate(["", ""]) == {"kind": "empty", "nulls": 2}


def test_primary_key_is_skipped():
    result = _accumulate(["1", "2"], declared="integer", skip_reason="primary_key")

    assert result == {"kind": "skipped", "reason": "primary_key"}


def test_declared_type_is_enforced():
    with pytest.raises(ValueError):
        _accumulate(["1", "abc"], declared="integer")


def test_table_sampler_reads_csv_and_uses_config(tmp_path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text(
        "id,amount,status,created_at\n"
        "1,100,NEW,2024-01-01\n"
        "2,100,DONE,2024-02-01\n"
        "3,250,NEW,2024-03-01\n",
        encoding="utf-8",
    )
    table = TableConfig(
        name="orders",
        row_count=3,
        columns=[
            ColumnConfig(name="id", type="integer", primary_key=True),
            ColumnConfig(name="amount", type="numeric"),
            ColumnConfig(name="status", type="varchar"),
            ColumnConfig(name="created_at", type="date"),
        ],
    )

    stat = TableSampler(SampleOptions()).sample_file(csv_path, table)

    assert stat["table"] == "orders"
    assert stat["rows"] == 3
    cols = stat["columns"]
    assert cols["id"] == {"kind": "skipped", "reason": "primary_key"}
    assert cols["amount"]["kind"] == "number"
    assert cols["amount"]["top"] == {"100": 2, "250": 1}
    assert cols["status"] == {"kind": "enum", "counts": {"NEW": 2, "DONE": 1}, "nulls": 0}
    assert cols["created_at"]["kind"] == "temporal"
    assert cols["created_at"]["from"] == "2024-01-01T00:00:00"


def test_table_sampler_without_config_infers_types(tmp_path):
    csv_path = tmp_path / "items.csv"
    csv_path.write_text("id,label\n1,a\n2,b\n", encoding="utf-8")

    stat = TableSampler(SampleOptions()).sample_file(csv_path)

    assert stat["columns"]["id"]["kind"] == "number"
    assert stat["columns"]["label"]["kind"] == "enum"


def test_write_stat_produces_json_file(tmp_path):
    out = tmp_path / "items.stat.json"
    write_stat({"table": "items", "rows": 1, "columns": {}}, out)

    assert json.loads(out.read_text(encoding="utf-8")) == {"table": "items", "rows": 1, "columns": {}}


def _fk_config():
    from datamultiplier.config import GenerationConfig

    return GenerationConfig(
        tables=[
            TableConfig(
                name="customers",
                row_count=5,
                columns=[ColumnConfig(name="id", type="integer", primary_key=True)],
            ),
            TableConfig(
                name="orders",
                row_count=8,
                columns=[
                    ColumnConfig(name="id", type="integer", primary_key=True),
                    ColumnConfig(name="customer_id", type="integer", foreign_key="customers.id"),
                ],
            ),
        ]
    )


def test_compute_relations_counts_children_per_parent(tmp_path):
    (tmp_path / "customers.csv").write_text("id\n1\n2\n3\n4\n5\n", encoding="utf-8")
    (tmp_path / "orders.csv").write_text(
        "id,customer_id\n1,1\n2,2\n3,2\n4,4\n5,4\n6,4\n7,4\n8,\n", encoding="utf-8"
    )

    relations, skipped = compute_relations("customers", tmp_path, _fk_config())

    assert skipped == []
    assert relations == {
        "orders.customer_id": {
            "child_rows": 8,
            "null": 1,
            "distribution": {"0": 2, "1": 1, "2": 1, "4": 1},
        }
    }


def test_compute_relations_reports_missing_child_csv(tmp_path):
    (tmp_path / "customers.csv").write_text("id\n1\n", encoding="utf-8")

    relations, skipped = compute_relations("customers", tmp_path, _fk_config())

    assert relations == {}
    assert skipped == ["orders.customer_id"]
