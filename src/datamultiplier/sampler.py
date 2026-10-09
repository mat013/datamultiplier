"""Column statistics for CSV files, written as <table>.stat.json."""

import csv
import json
import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from .config import ColumnConfig, TableConfig

MAX_TRACKED = 10_000
SAMPLE_SEED = 42

NUMBER_TYPES = {
    "integer", "int", "int2", "int4", "int8", "smallint", "bigint", "serial", "bigserial",
    "numeric", "decimal", "real", "float", "float4", "float8", "double precision", "money",
}
TEMPORAL_TYPES = {
    "date", "timestamp", "timestamp without time zone", "timestamp with time zone", "timestamptz",
}
TEXT_TYPES = {
    "text", "varchar", "character varying", "char", "character", "bpchar", "citext", "uuid",
}


@dataclass(frozen=True)
class SampleOptions:
    max_text_length: int = 70
    max_distinct: int = 20
    max_samples: int = 20
    top: int = 10


def _declared_kind(declared: Optional[str]) -> Optional[str]:
    if not declared:
        return None
    t = declared.lower()
    if t in NUMBER_TYPES:
        return "number"
    if t in TEMPORAL_TYPES:
        return "temporal"
    if t in TEXT_TYPES:
        return "text"
    return None


def _parse_number(raw: str) -> Optional[Decimal]:
    try:
        d = Decimal(raw)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _parse_temporal(raw: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _json_number(d: Decimal) -> int | float:
    return int(d) if d == d.to_integral_value() else float(d)


def _skip_reason(col: Optional[ColumnConfig]) -> Optional[str]:
    if col is None:
        return None
    if col.primary_key:
        return "primary_key"
    if col.foreign_key:
        return "foreign_key"
    if col.auto_increment:
        return "auto_increment"
    return None


class ColumnAccumulator:
    """Collects statistics for one column in a streaming pass."""

    def __init__(
        self,
        name: str,
        declared_type: Optional[str],
        options: SampleOptions,
        rng: random.Random,
        skip_reason: Optional[str] = None,
    ):
        self.name = name
        self.options = options
        self.rng = rng
        self.skip_reason = skip_reason
        self.forced = _declared_kind(declared_type)

        self.nulls = 0
        self.seen = 0
        self.max_len = 0
        self.counts: Counter[str] = Counter()
        self.truncated = False
        self.samples: list[str] = []

        self.numeric_ok = self.forced in (None, "number")
        self.temporal_ok = self.forced in (None, "temporal")
        self.num_min: Optional[Decimal] = None
        self.num_max: Optional[Decimal] = None
        self.time_min: Optional[datetime] = None
        self.time_max: Optional[datetime] = None

    def add(self, raw: str) -> None:
        if self.skip_reason:
            return
        if raw == "":
            self.nulls += 1
            return

        self.seen += 1
        self.max_len = max(self.max_len, len(raw))
        self._count(raw)
        self._reservoir(raw)

        if self.numeric_ok:
            d = _parse_number(raw)
            if d is None:
                self._reject("number", raw)
            else:
                self.num_min = d if self.num_min is None else min(self.num_min, d)
                self.num_max = d if self.num_max is None else max(self.num_max, d)

        if self.temporal_ok:
            t = _parse_temporal(raw)
            if t is None:
                self._reject("temporal", raw)
            else:
                self.time_min = t if self.time_min is None else min(self.time_min, t)
                self.time_max = t if self.time_max is None else max(self.time_max, t)

    def _reject(self, kind: str, raw: str) -> None:
        if self.forced is not None:
            raise ValueError(
                f"Kolonne '{self.name}' er angivet som {self.forced}, men '{raw}' er ikke gyldig"
            )
        if kind == "number":
            self.numeric_ok = False
            self.num_min = self.num_max = None
        else:
            self.temporal_ok = False
            self.time_min = self.time_max = None

    def _count(self, raw: str) -> None:
        if raw in self.counts:
            self.counts[raw] += 1
        elif len(self.counts) < MAX_TRACKED:
            self.counts[raw] = 1
        else:
            self.truncated = True

    def _reservoir(self, raw: str) -> None:
        limit = self.options.max_samples
        if limit <= 0:
            return
        if len(self.samples) < limit:
            self.samples.append(raw)
            return
        j = self.rng.randrange(self.seen)
        if j < limit:
            self.samples[j] = raw

    def result(self) -> dict[str, Any]:
        if self.skip_reason:
            return {"kind": "skipped", "reason": self.skip_reason}
        if self.seen == 0:
            return {"kind": "empty", "nulls": self.nulls}

        kind = self._decide_kind()
        if kind == "number":
            return self._number_result()
        if kind == "temporal":
            return {
                "kind": "temporal",
                "from": self.time_min.isoformat(),
                "to": self.time_max.isoformat(),
                "nulls": self.nulls,
            }
        return self._text_result()

    def _decide_kind(self) -> str:
        if self.numeric_ok and (self.forced is None or self.forced == "number"):
            return "number"
        if self.temporal_ok and (self.forced is None or self.forced == "temporal"):
            return "temporal"
        return "text"

    def _number_result(self) -> dict[str, Any]:
        distinct = len(self.counts)
        if distinct <= self.options.max_distinct and not self.truncated:
            top_n = distinct
        else:
            top_n = self.options.top
        result: dict[str, Any] = {
            "kind": "number",
            "from": _json_number(self.num_min),
            "to": _json_number(self.num_max),
            "nulls": self.nulls,
            "top": dict(self.counts.most_common(top_n)),
        }
        if self.truncated:
            result["truncated"] = True
        return result

    def _text_result(self) -> dict[str, Any]:
        distinct = len(self.counts)
        if (
            self.max_len <= self.options.max_text_length
            and distinct <= self.options.max_distinct
            and not self.truncated
        ):
            return {"kind": "enum", "counts": dict(self.counts.most_common()), "nulls": self.nulls}
        return {"kind": "text", "samples": list(self.samples), "nulls": self.nulls}


class TableSampler:
    """Streams a CSV file once and produces per-column statistics."""

    def __init__(self, options: SampleOptions):
        self.options = options

    def sample_file(
        self, csv_path: Path, table_config: Optional[TableConfig] = None
    ) -> dict[str, Any]:
        rng = random.Random(SAMPLE_SEED)
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                raise ValueError(f"CSV-filen er tom: {csv_path}")

            accumulators = []
            for name in header:
                col = table_config.get_column(name) if table_config else None
                declared = col.type if col else None
                accumulators.append(
                    ColumnAccumulator(name, declared, self.options, rng, _skip_reason(col))
                )

            rows = 0
            for row in reader:
                rows += 1
                for i, acc in enumerate(accumulators):
                    acc.add(row[i] if i < len(row) else "")

        return {
            "table": csv_path.stem,
            "rows": rows,
            "columns": {acc.name: acc.result() for acc in accumulators},
        }


def write_stat(stat: dict[str, Any], out_path: Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stat, f, indent=2, ensure_ascii=False)
