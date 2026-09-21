# datamultiplier

PostgreSQL test data generator for large-scale relational datasets. Creates 1M+ rows across 10-15 related tables with customizable data generation rules.

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
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

```bash
datamultiplier generate --db-url postgresql://user:pass@localhost/mydb --config schema.yaml --rows 1000000 --seed 42
```

#### 4. Dump Data

Export generated data to CSV:

```bash
datamultiplier dump --db-url postgresql://user:pass@localhost/mydb --table users --output users.csv
```

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

