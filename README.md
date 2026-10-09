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

