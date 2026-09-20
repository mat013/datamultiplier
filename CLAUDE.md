# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**datamultiplier** is a Python CLI tool for generating and managing large-scale test data in PostgreSQL databases. It creates realistic, relational test datasets (1M+ rows across 10-15 related tables) and provides utilities to inspect database schemas, configure data generation, and export/dump data.

### Why Python?
The organization has blacklisted certain npm packages, but Python dependencies remain unrestricted. This project leverages Python to bypass package restrictions while maintaining full functionality.

## Core Workflow

The tool operates as a series of CLI commands executed sequentially:

1. **Inspect** — Read PostgreSQL schema (tables, columns, relationships, constraints) and output as YAML config
2. **Configure** — User reviews/modifies the generated YAML to customize data generation rules
3. **Generate** — Create 1M+ test rows based on the YAML config, respecting foreign key relationships
4. **Dump** — Export generated data (full tables, subsets, or formats)

## Tech Stack

- **Python 3.8+** (or latest stable)
- **PostgreSQL** (via psycopg2 or asyncpg for performance at scale)
- **YAML** (PyYAML) — configuration format
- **CLI framework** (Click or argparse) — command-line interface
- **Type hints** (dataclasses or Pydantic) — schema/config structures
- **Faker** (optional) — for realistic synthetic data generation

## Project Structure

```
datamultiplier/
├── pyproject.toml          # Project metadata, dependencies, entry point
├── README.md               # User-facing documentation
├── src/
│   └── datamultiplier/
│       ├── __init__.py
│       ├── cli.py          # Main CLI entry point (Click/argparse commands)
│       ├── inspector.py    # Inspect DB schema → YAML
│       ├── generator.py    # Generate data from YAML config
│       ├── dumper.py       # Export/dump data from tables
│       ├── config.py       # YAML config structures (Pydantic/dataclass)
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py  # PostgreSQL connection pooling & utils
│       │   └── queries.py     # Prepared queries, bulk insert helpers
│       └── utils/
│           ├── __init__.py
│           ├── faker_helpers.py  # Custom Faker providers
│           └── validators.py     # Config validation
├── tests/
│   ├── conftest.py         # Pytest fixtures (test DB setup)
│   ├── test_inspector.py
│   ├── test_generator.py
│   ├── test_dumper.py
│   └── integration/        # Full workflow tests
└── examples/
    └── sample_schema.yaml  # Example config for a typical 3-table schema
```

## Common Development Commands

```bash
# Install in development mode with test dependencies
pip install -e ".[dev,test]"

# Run tests (all or single file)
pytest
pytest tests/test_generator.py

# Run a single test
pytest tests/test_generator.py::test_bulk_insert_performance -v

# Type check
mypy src/

# Lint/format
black src/ tests/
flake8 src/ tests/
ruff check src/

# Run the CLI locally
python -m datamultiplier.cli --help
```

## CLI Command Structure

Each command maps to a module:

```bash
# 1. Inspect database schema → schema.yaml
python -m datamultiplier.cli inspect --db-url postgresql://user:pass@localhost/mydb --output schema.yaml

# 2. (User edits schema.yaml to customize data generation rules)

# 3. Generate data from config
python -m datamultiplier.cli generate --db-url postgresql://user:pass@localhost/mydb --config schema.yaml --rows 1000000

# 4. Dump data (full table, CSV, or partial query)
python -m datamultiplier.cli dump --db-url postgresql://user:pass@localhost/mydb --table users --format csv --output users.csv
```

## Key Architectural Notes

### Relationship Handling
- Inspect phase extracts foreign key constraints and generates YAML metadata
- Generate phase respects FK relationships: parent records inserted before children
- Use database-level cascading rules or manual dependency ordering in generator

### Performance at 1M+ Rows
- **Bulk inserts** — use `COPY` or batch `INSERT` statements (not row-by-row)
- **Connection pooling** — reuse DB connections efficiently
- **Transactions** — group inserts into large transactions to minimize overhead
- **Indexes** — turn off during generation, rebuild after; or use `maintenance_work_mem`

### YAML Config Schema
The generated YAML should include:
- Table definitions (name, row count)
- Column specs (type, constraints, faker rule)
- Relationships (FK references to parent tables)
- Seeding options (fixed seeds for reproducibility)

Example:
```yaml
tables:
  users:
    row_count: 100000
    columns:
      id: { type: integer, primary_key: true, auto_increment: true }
      name: { type: varchar, faker: name }
      email: { type: varchar, faker: email, unique: true }
  orders:
    row_count: 500000
    columns:
      id: { type: integer, primary_key: true }
      user_id: { type: integer, foreign_key: users.id }
      amount: { type: numeric, faker: "random_int(10, 9999)" }
```

### Configuration Flow
1. `inspector.py` introspects live DB, constructs config programmatically
2. Serializes to YAML with sensible defaults (Faker rules, row counts, etc.)
3. User edits YAML manually (adjust row counts, customize data patterns)
4. `generator.py` reads YAML, validates, and inserts data respecting constraints

## Testing Strategy

- **Unit tests** — Test inspector parsing, config validation, data generation rules in isolation
- **Integration tests** — Spin up test PostgreSQL (docker-compose or fixture), run full inspect→generate→dump workflow
- **Performance tests** — Verify bulk insert handles 1M rows within acceptable time/memory

## Database Considerations

- Assumes PostgreSQL 12+ (or adapt for specific version constraints)
- Connection string passed via `--db-url` CLI flag or `DB_URL` env var
- Scripts should handle schema existence checks and optional table truncation before generate
- Dump operations should NOT modify source schema (read-only)

## Common Issues & Patterns

- **Foreign key constraint violations** — Ensure parent rows exist before children; order table generation by dependency depth
- **Reproducibility** — Accept `--seed` parameter to seed RNG for deterministic fake data across runs
- **Large exports** — Stream CSV writes to avoid loading entire result set in memory
- **Connection timeouts** — Use connection pooling and reasonable statement timeouts for long-running operations

## Next Steps for Development

1. Set up project structure and `pyproject.toml` with dependencies
2. Implement `db/connection.py` (connection pooling, query builders)
3. Build `inspector.py` (extract schema from PostgreSQL system tables)
4. Design YAML config schema and implement `config.py` validators
5. Implement `generator.py` (bulk insert logic, FK ordering)
6. Implement `dumper.py` (CSV/JSON export)
7. Wire CLI commands in `cli.py`
8. Add comprehensive tests with a test database fixture
