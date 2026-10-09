# datamultiplier

PostgreSQL test data generator for large-scale relational datasets. Creates 1M+ rows across 10-15 related tables with customizable data generation rules.

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Environment Configuration

To avoid repeating database connection arguments, create a `.env` file in your project root:

```bash
# .env
DATABASE_URL=postgresql://user:pass@localhost/mydb
```

The tool automatically loads variables from `.env` at startup. You can then omit `--db-url` from commands:

```bash
# Uses DATABASE_URL from .env
datamultiplier inspect --output schema.yaml
datamultiplier generate --config schema.yaml
```

Or override any variable from the command line:
```bash
# This takes precedence over .env
datamultiplier inspect --db-url postgresql://other:host/db --output schema.yaml
```

### Usage

#### 1. Inspect Database Schema

Reads PostgreSQL schema and generates a YAML configuration file:

```bash
datamultiplier inspect --db-url postgresql://user:pass@localhost/mydb --output schema.yaml
```

#### 2. Customize Configuration (Optional)

Edit `schema.yaml` to customize row counts, data generation rules, and relationships.

#### 3. Generate Test Data

For faster bulk inserts, you can temporarily disable foreign key constraints:

```bash
# Disable constraints before generation
datamultiplier disable-fks --db-url postgresql://user:pass@localhost/mydb

# Generate data (much faster without FK checks)
datamultiplier generate --db-url postgresql://user:pass@localhost/mydb --config schema.yaml --rows 1000000 --seed 42

# Re-enable constraints after generation
datamultiplier enable-fks --db-url postgresql://user:pass@localhost/mydb
```

Or run without disabling constraints (slower but validates as you go):

```bash
datamultiplier generate --db-url postgresql://user:pass@localhost/mydb --config schema.yaml --rows 1000000 --seed 42
```

#### 4. Dump Data

Export generated data to CSV:

**Single table:**
```bash
datamultiplier dump --db-url postgresql://user:pass@localhost/mydb --table users --output users.csv
```

**All tables:**
```bash
# Dump all tables in the database
datamultiplier dump-all --db-url postgresql://user:pass@localhost/mydb --output-dir ./data

# Or dump only tables defined in schema.yaml
datamultiplier dump-all --db-url postgresql://user:pass@localhost/mydb --config schema.yaml --output-dir ./data
```

#### 4b. Load Data from CSV

Load CSV files back into the database (reverse of `dump`):

**Single file:**
```bash
datamultiplier load --db-url postgresql://user:pass@localhost/mydb --input users.csv --table users
```

**Directory (all CSV files):**
```bash
# Load all CSV files from a directory
datamultiplier load --db-url postgresql://user:pass@localhost/mydb --input ./data

# For faster loading with FK constraints, disable them first
datamultiplier load --db-url postgresql://user:pass@localhost/mydb --input ./data --disable-fks --enable-fks

# Load and replace existing data (truncate tables first)
datamultiplier load --db-url postgresql://user:pass@localhost/mydb --input ./data --truncate
```

**Workflow example (dump and reload):**
```bash
# Dump all tables
datamultiplier dump-all --db-url postgresql://user:pass@localhost/mydb --output-dir ./backup

# (Later) reload them, replacing all existing data
datamultiplier load --db-url postgresql://user:pass@localhost/mydb --input ./backup --truncate --disable-fks --enable-fks
```

#### 4c. Sample Column Statistics (Optional)

Analyse the CSV files from `dump-all` and write a `<table>.stat.json` next to each CSV, describing the values in every column. No database connection is needed.

```bash
datamultiplier samples --csv-dir ./data --config schema.yaml
datamultiplier samples --csv-dir ./data --table orders --max-text-length 50 --max-distinct 30
```

How each column is described:

- **Primary key, foreign key, auto increment** (from `--config`): `skipped`. No range is calculated for ids.
- **Numbers**: `from`/`to` (min/max) and `top`, the most frequent values. If the column has at most `--max-distinct` distinct values, `top` contains all of them, so the full distribution is shown.
- **Dates and timestamps**: `from`/`to` as ISO strings.
- **Short text** (every value at most `--max-text-length` characters) with at most `--max-distinct` distinct values: `enum` with the count of each value.
- **Long text, or text with too many distinct values**: `text` with up to `--max-samples` example values.
- **Empty cells** are counted as `nulls`. A column with only empty cells is `empty`.

Without `--config` the column type is inferred from the values, and no column is skipped. Numbers with many distinct values are then reported with `top` and `truncated: true`.

Example output:
```json
{
  "table": "orders",
  "rows": 1000000,
  "columns": {
    "id":         {"kind": "skipped", "reason": "primary_key"},
    "amount":     {"kind": "number", "from": 10, "to": 9999, "nulls": 0, "top": {"100": 4200, "250": 3100}},
    "created_at": {"kind": "temporal", "from": "2023-01-01T00:00:00", "to": "2024-12-31T00:00:00", "nulls": 0},
    "status":     {"kind": "enum", "counts": {"NEW": 500, "DONE": 300}, "nulls": 0},
    "notes":      {"kind": "text", "samples": ["lang tekst 1", "..."], "nulls": 12}
  }
}
```

The statistics are streamed once per file, so memory use stays flat for large CSV files.

**Relations:** When `--config` is given, each parent table's `.stat.json` also gets a `relations` section with one entry per foreign key pointing at it. `distribution` shows how many parent rows have 0, 1, 2 ... children:

```json
"relations": {
  "orders.customer_id": {
    "child_rows": 8,
    "null": 1,
    "distribution": {"0": 2, "1": 1, "2": 1, "4": 1}
  }
}
```

Here 2 customers have no orders, 1 customer has 1 order, 1 customer has 2 orders, and 1 customer has 4 orders. If a child CSV is missing, that relation is skipped and reported.

#### 4d. Extract Related Rows (Reproduce a Problem)

Given one row, extract every row connected to it through foreign keys, followed recursively in both directions (parents up, children down). The result is written as one CSV per table, in the same format as `dump-all`:

```bash
datamultiplier extract --table orders --id 12345 --output-dir ./repro --max-rows 10000
```

The extraction runs in a single read-only, repeatable-read transaction, so the result is a consistent snapshot and the source database is not changed. Tables are listed in breadth-first order from the seed row, and self-references and cycles are handled.

**Moving the data to another environment:**
```bash
# In the other environment, with an empty copy of the schema
datamultiplier load --db-url postgresql://user:pass@other-host/mydb --input ./repro --disable-fks --enable-fks
```

**Limits:**
- `--max-rows` is a safety brake on the total number of rows. When it is reached the output is marked as incomplete and a warning is printed. Parent rows may then be missing, so use `load --disable-fks` without `--enable-fks`, or raise the limit.
- `--id-column` is needed if the table has no single primary key, or if the id refers to another column.
- The output directory must be empty or not exist.

#### 5. Convert to Object Format (Optional)

Transform relational CSV data into objects with relationship indices. Each row becomes a JSON object showing which rows it relates to via foreign keys:

```bash
datamultiplier objectify --csv-dir ./data --config schema.yaml --output objects.jsonl
```

Output format:
```json
{
  "table": "account",
  "id": "1",
  "relates": {
    "app_user": ["1"],
    "trade": ["10", "11"],
    "movement": ["100", "101", "102"]
  }
}
```

#### 6. Group Related Objects (Optional)

Cluster related rows into connected components using union-find. Useful for understanding which rows form a logical entity across multiple tables:

```bash
datamultiplier group-objects --input objects.jsonl --output grouped.jsonl
```

Output format:
```json
{
  "object_id": "account_1",
  "members": {
    "account": ["1"],
    "app_user": ["1"],
    "trade": ["10", "11"],
    "movement": ["100", "101", "102"]
  }
}
```

Handles circular foreign key relationships automatically.

## Development

### Running Tests

```bash
pytest
```

### Linting & Formatting

```bash
black src/ tests/
flake8 src/ tests/
ruff check src/
mypy src/
```

## License

MIT

