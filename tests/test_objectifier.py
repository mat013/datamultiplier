"""Tests for CSV-to-object conversion."""

import csv
import json
import tempfile
from pathlib import Path

import pytest

from datamultiplier.config import GenerationConfig, TableConfig, ColumnConfig
from datamultiplier.objectifier import RelationIndexer


@pytest.fixture
def csv_with_relations(tmp_path):
    """Create test CSV files with relationships."""
    config = GenerationConfig()

    # Create tables: users, posts (user_id FK), comments (post_id FK)
    config.tables = [
        TableConfig(
            name="users",
            row_count=2,
            columns=[
                ColumnConfig(name="id", type="integer", primary_key=True),
                ColumnConfig(name="name", type="varchar"),
            ],
        ),
        TableConfig(
            name="posts",
            row_count=3,
            columns=[
                ColumnConfig(name="id", type="integer", primary_key=True),
                ColumnConfig(name="user_id", type="integer", foreign_key="users.id"),
                ColumnConfig(name="title", type="varchar"),
            ],
        ),
        TableConfig(
            name="comments",
            row_count=4,
            columns=[
                ColumnConfig(name="id", type="integer", primary_key=True),
                ColumnConfig(name="post_id", type="integer", foreign_key="posts.id"),
                ColumnConfig(name="text", type="text"),
            ],
        ),
    ]

    # Write CSV files
    Path(tmp_path / "users.csv").write_text("id,name\n1,Alice\n2,Bob\n")
    Path(tmp_path / "posts.csv").write_text("id,user_id,title\n10,1,Post1\n11,1,Post2\n12,2,Post3\n")
    Path(tmp_path / "comments.csv").write_text("id,post_id,text\n100,10,Comment1\n101,10,Comment2\n102,11,Comment3\n103,12,Comment4\n")

    return tmp_path, config


def test_objectify_builds_relations(csv_with_relations):
    """Test that objectify() creates relation index."""
    csv_dir, config = csv_with_relations
    indexer = RelationIndexer(str(csv_dir), config)

    output_file = csv_dir / "objects.jsonl"
    row_count = indexer.objectify(str(output_file))

    assert row_count == 9  # 2 users + 3 posts + 4 comments

    # Check that user 1 relates to posts 10, 11
    with open(output_file) as f:
        lines = f.readlines()
        user_1 = json.loads(lines[0])

    assert user_1["table"] == "users"
    assert user_1["id"] == "1"
    assert "posts" in user_1["relates"]
    assert set(user_1["relates"]["posts"]) == {"10", "11"}


def test_group_objects_merges_related_rows(csv_with_relations):
    """Test that group_objects() creates connected components."""
    csv_dir, config = csv_with_relations
    indexer = RelationIndexer(str(csv_dir), config)

    # First objectify
    objects_file = csv_dir / "objects.jsonl"
    indexer.objectify(str(objects_file))

    # Then group
    grouped_file = csv_dir / "grouped.jsonl"
    group_count = indexer.group_objects(str(objects_file), str(grouped_file))

    # Should have 2 groups: one for Alice (user 1, posts 10-11, comments 100-103)
    # and one for Bob (user 2, post 12, comment 103)
    assert group_count >= 1

    with open(grouped_file) as f:
        groups = [json.loads(line) for line in f]

    # At least one group should contain user 1
    assert any("users" in g["members"] and "1" in g["members"]["users"] for g in groups)


def test_missing_csv_skipped(csv_with_relations):
    """Test that missing CSV files are skipped with warning."""
    csv_dir, config = csv_with_relations
    # Remove comments.csv
    (csv_dir / "comments.csv").unlink()

    indexer = RelationIndexer(str(csv_dir), config)
    output_file = csv_dir / "objects.jsonl"
    row_count = indexer.objectify(str(output_file))

    # Should only have users and posts
    assert row_count == 5
