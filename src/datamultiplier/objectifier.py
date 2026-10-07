"""Convert relational CSV data to object-oriented JSON format with relationships."""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from collections import defaultdict

from .config import GenerationConfig


class RelationIndexer:
    """Analyzes CSV files and builds a relationship index."""

    def __init__(self, csv_dir: str, config: GenerationConfig):
        """Initialize indexer.

        Args:
            csv_dir: Directory containing CSV files
            config: GenerationConfig with FK metadata
        """
        self.csv_dir = csv_dir
        self.config = config
        self.pk_columns = {}  # table -> primary_key_column
        self.fk_mapping = {}  # (table, fk_col) -> (ref_table, ref_pk)
        self._build_metadata()

    def _build_metadata(self) -> None:
        """Extract primary keys and foreign keys from config."""
        for table in self.config.tables:
            pk_col = None
            for col in table.columns:
                if col.primary_key:
                    pk_col = col.name
                    break
            if pk_col:
                self.pk_columns[table.name] = pk_col

            for col in table.columns:
                if col.foreign_key:
                    ref_table, ref_col = col.foreign_key.split(".")
                    self.fk_mapping[(table.name, col.name)] = (ref_table, ref_col)

    def objectify(self, output_path: str) -> int:
        """Read CSVs and write objects with relationships as JSONL.

        Args:
            output_path: Path to output JSONL file

        Returns:
            Number of rows written
        """
        # First pass: build reverse FK index (child_table -> [(parent_table, child_fk_col)])
        child_fks = defaultdict(list)
        for (child_table, fk_col), (parent_table, parent_pk) in self.fk_mapping.items():
            child_fks[parent_table].append((child_table, fk_col, parent_pk))

        # Read all CSVs and index by (table, id)
        all_rows = {}
        for table in self.config.tables:
            csv_path = Path(self.csv_dir) / f"{table.name}.csv"
            if not csv_path.exists():
                print(f"  ⚠️  CSV not found: {csv_path}")
                continue

            if table.name not in self.pk_columns:
                print(f"  ⚠️  Skipping '{table.name}': no primary key")
                continue

            all_rows[table.name] = {}
            pk_col = self.pk_columns[table.name]

            with open(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_id = str(row[pk_col])
                    all_rows[table.name][row_id] = row

        # Write objects with relations
        row_count = 0
        with open(output_path, "w") as f:
            for table_name, rows in all_rows.items():
                pk_col = self.pk_columns[table_name]

                for row_id, row in rows.items():
                    relates = defaultdict(list)

                    # Add parents (rows this row points to via FK)
                    for col_name, (parent_table, parent_pk) in self.fk_mapping.items():
                        if col_name.split("_")[0] == table_name or True:  # Check if FK is in this table
                            for (tbl, fk_col, _), (ref_tbl, _) in self.fk_mapping.items():
                                if tbl == table_name and ref_tbl == parent_table:
                                    parent_id = row.get(fk_col)
                                    if parent_id:
                                        relates[parent_table].append(str(parent_id))

                    # Add children (rows that point to this row via FK)
                    for child_table, fk_col, _ in child_fks.get(table_name, []):
                        for child_id, child_row in all_rows.get(child_table, {}).items():
                            if str(child_row.get(fk_col)) == row_id:
                                relates[child_table].append(child_id)

                    # Deduplicate and sort
                    relates = {
                        k: sorted(list(set(v))) for k, v in relates.items() if v
                    }

                    obj = {
                        "table": table_name,
                        "id": row_id,
                        "relates": relates,
                    }
                    f.write(json.dumps(obj) + "\n")
                    row_count += 1

        return row_count

    def group_objects(self, input_path: str, output_path: str) -> int:
        """Group related rows into connected components using union-find.

        Args:
            input_path: Path to JSONL from objectify()
            output_path: Path to output grouped objects

        Returns:
            Number of groups written
        """
        parent = {}  # (table, id) -> representative

        def find(key):
            if key not in parent:
                parent[key] = key
            if parent[key] != key:
                parent[key] = find(parent[key])
            return parent[key]

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # First pass: union all related rows
        with open(input_path) as f:
            for line in f:
                obj = json.loads(line)
                table, obj_id = obj["table"], obj["id"]
                key = (table, obj_id)
                find(key)

                for rel_table, rel_ids in obj.get("relates", {}).items():
                    for rel_id in rel_ids:
                        union(key, (rel_table, rel_id))

        # Second pass: group by representative
        groups = defaultdict(lambda: defaultdict(list))
        with open(input_path) as f:
            for line in f:
                obj = json.loads(line)
                table, obj_id = obj["table"], obj["id"]
                rep = find((table, obj_id))
                groups[rep][table].append(obj_id)

        # Write grouped objects
        group_count = 0
        with open(output_path, "w") as f:
            for rep, members in groups.items():
                group_obj = {
                    "object_id": f"{rep[0]}_{rep[1]}",
                    "members": dict(members),
                }
                f.write(json.dumps(group_obj) + "\n")
                group_count += 1

        return group_count
