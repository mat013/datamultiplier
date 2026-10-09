"""Command-line interface for datamultiplier."""

import click
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from .db.connection import DatabaseConnection
from .inspector import SchemaInspector
from .generator import DataGenerator
from .dumper import DataDumper
from .loader import DataLoader
from .config import GenerationConfig
from .objectifier import RelationIndexer


def disable_foreign_keys(db: DatabaseConnection, state_file: str) -> list[dict]:
    """Disable all FK constraints and save definitions.

    Args:
        db: Database connection
        state_file: Path to save FK definitions

    Returns:
        List of FK definitions saved

    Raises:
        click.Abort if state_file already exists
    """
    if Path(state_file).exists():
        click.echo(f"✗ State file '{state_file}' already exists.")
        raise click.Abort()

    fk_defs = db.get_fk_definitions()
    if not fk_defs:
        click.echo(f"No foreign keys found")
        return []

    click.echo(f"Disabling {len(fk_defs)} foreign keys...")
    for fk in fk_defs:
        table = fk["table_name"]
        constraint = fk["constraint_name"]
        db.drop_fk(table, constraint)
        click.echo(f"  ✓ Dropped {table}.{constraint}")

    # Save definitions to state file
    state_data = [
        {
            "table_name": fk["table_name"],
            "constraint_name": fk["constraint_name"],
            "definition": fk["definition"],
        }
        for fk in fk_defs
    ]

    with open(state_file, "w") as f:
        json.dump(state_data, f, indent=2)

    return state_data


def enable_foreign_keys(db: DatabaseConnection, state_file: str, not_valid: bool = False) -> None:
    """Re-enable FK constraints from state file.

    Args:
        db: Database connection
        state_file: Path to FK definitions (from disable_foreign_keys)
        not_valid: If True, add constraints NOT VALID (faster, but leaves them invalid)

    Raises:
        click.Abort if any constraint cannot be re-added
    """
    if not Path(state_file).exists():
        click.echo(f"✗ State file '{state_file}' not found")
        raise click.Abort()

    with open(state_file, "r") as f:
        state_data = json.load(f)

    click.echo(f"Re-enabling {len(state_data)} foreign keys...")

    failed = False
    for item in state_data:
        table = item["table_name"]
        constraint = item["constraint_name"]
        definition = item["definition"]

        try:
            db.add_fk(table, constraint, definition, not_valid=not_valid)
            click.echo(f"  ✓ Added {table}.{constraint}")
        except Exception as e:
            click.echo(f"  ✗ Failed to add {table}.{constraint}")
            click.echo(f"    Error: {e}")
            failed = True

    if failed:
        click.echo(f"✗ Some constraints could not be re-enabled")
        click.echo(f"   Fix the data and try again")
        raise click.Abort()

    # Clean up state file on success
    Path(state_file).unlink()
    click.echo(f"✓ All {len(state_data)} foreign keys re-enabled")


@click.group()
def main() -> None:
    """PostgreSQL test data generator for large-scale relational datasets.

    Quick Start:
        1. Inspect your database schema:
            datamultiplier inspect --db-url postgresql://user:pass@localhost/db \\
                --schema my_schema

        2. Edit schema.yaml to customize row counts and data generation rules

        3. Generate test data:
            datamultiplier generate --db-url postgresql://user:pass@localhost/db \\
                --schema my_schema --config schema.yaml --rows 1000000

        4. Export data:
            datamultiplier dump-all --db-url postgresql://user:pass@localhost/db \\
                --schema my_schema --output-dir ./backups

    Schema: By default, uses the user's search_path. Use --schema to override.

    Use --help with any command for more details:
        datamultiplier inspect --help
        datamultiplier generate --help
        datamultiplier dump --help
    """
    pass


@main.command()
@click.option(
    "--db-url",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL connection URL (e.g., postgresql://user:pass@localhost/db)",
)
@click.option(
    "--schema",
    default=None,
    help="Database schema name (default: user's search_path)",
)
@click.option(
    "--output",
    type=click.Path(),
    default="schema.yaml",
    help="Output YAML file path",
)
def inspect(db_url: str, schema: str, output: str) -> None:
    """Inspect database schema and generate YAML configuration.

    This command connects to a PostgreSQL database, reads all tables and their
    relationships, and generates a YAML configuration file that can be customized
    before data generation.
    """
    click.echo(f"Connecting to database...")
    click.echo(f"  Schema: {schema}")
    click.echo(f"  Output: {output}")

    db = DatabaseConnection(db_url, schema=schema)
    db.connect()
    click.echo(f"✓ Connected")

    try:
        click.echo(f"\nInspecting schema '{schema}'...")
        inspector = SchemaInspector(db)
        config = inspector.inspect_all_tables()

        click.echo(f"\n✓ Found {len(config.tables)} tables")
        click.echo(f"\nGenerating configuration...")
        config.to_yaml(output)
        click.echo(f"✓ Configuration saved to '{output}'")

        click.echo(f"\nNext: Edit '{output}' to customize row counts and data rules, then run:")
        click.echo(f"  datamultiplier generate --db-url {db_url} --schema {schema} --config {output}")

    finally:
        db.disconnect()


@main.command()
@click.option(
    "--db-url",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL connection URL",
)
@click.option(
    "--schema",
    default=None,
    help="Database schema name (default: user's search_path)",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    required=True,
    help="YAML configuration file",
)
@click.option(
    "--rows",
    type=int,
    help="Override row count for all tables (optional)",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    help="Random seed for reproducible data generation",
)
def generate(db_url: str, schema: str, config: str, rows: int, seed: int) -> None:
    """Generate test data based on YAML configuration.

    This command reads a YAML configuration file (typically generated by the
    'inspect' command) and generates large-scale test data respecting foreign
    key relationships and data generation rules.

    Example:
        datamultiplier generate --db-url postgresql://user:pass@localhost/mydb \\
            --config schema.yaml --rows 1000000 --seed 42
    """
    click.echo(f"Loading configuration from '{config}'...")

    config_obj = GenerationConfig.from_yaml(config)
    config_obj.seed = seed

    # Override row counts if specified
    if rows:
        for table in config_obj.tables:
            table.row_count = rows

    click.echo(f"\nGeneration settings:")
    click.echo(f"  Schema: {schema}")
    click.echo(f"  Seed: {config_obj.seed}")
    click.echo(f"\nTables to generate:")
    total_rows = 0
    for table in config_obj.tables:
        click.echo(f"  - {table.name}: {table.row_count:,} rows")
        total_rows += table.row_count
    click.echo(f"\nTotal: {total_rows:,} rows")

    if not click.confirm("Proceed with data generation?"):
        click.echo("Cancelled.")
        return

    click.echo(f"\nConnecting to database schema '{schema}'...")
    db = DatabaseConnection(db_url, schema=schema)
    db.connect()
    click.echo(f"✓ Connected")

    try:
        generator = DataGenerator(db, config_obj)
        generator.generate_all()

        click.echo(f"\n✓ Data generation complete!")
        click.echo(f"Generated {total_rows:,} rows across {len(config_obj.tables)} tables")

    finally:
        db.disconnect()


@main.command()
@click.option(
    "--db-url",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL connection URL",
)
@click.option(
    "--schema",
    default=None,
    help="Database schema name (default: user's search_path)",
)
@click.option(
    "--table",
    required=True,
    help="Table name to export",
)
@click.option(
    "--output",
    type=click.Path(),
    required=True,
    help="Output file path",
)
@click.option(
    "--format",
    type=click.Choice(["csv", "sql"]),
    default="csv",
    help="Export format",
)
@click.option(
    "--where",
    help="Optional WHERE clause to filter rows",
)
def dump(db_url: str, schema: str, table: str, output: str, format: str, where: str) -> None:
    """Export table data to CSV or SQL.

    Examples:
        # Export entire table to CSV
        datamultiplier dump --db-url postgresql://user:pass@localhost/mydb \\
            --table users --output users.csv

        # Export filtered data to SQL
        datamultiplier dump --db-url postgresql://user:pass@localhost/mydb \\
            --table orders --output recent_orders.sql --format sql \\
            --where "created_at > '2024-01-01'"
    """
    click.echo(f"Exporting table '{schema}.{table}' to {format.upper()}...")
    click.echo(f"  Output: {output}")

    db = DatabaseConnection(db_url, schema=schema)
    db.connect()
    click.echo(f"✓ Connected")

    try:
        dumper = DataDumper(db)

        if format == "csv":
            dumper.dump_table_to_csv(table, output, where_clause=where)
        elif format == "sql":
            dumper.dump_table_to_sql(table, output, where_clause=where)

        click.echo(f"✓ Export complete: {output}")

    finally:
        db.disconnect()


@main.command()
@click.option(
    "--db-url",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL connection URL",
)
@click.option(
    "--schema",
    default=None,
    help="Database schema name (default: user's search_path)",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=None,
    help="YAML config file to specify which tables to dump (default: all tables)",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default="./data_dump",
    help="Output directory for CSV files",
)
def dump_all(db_url: str, schema: str, config: str, output_dir: str) -> None:
    """Export tables to CSV files.

    By default exports all tables in the database. If --config is provided,
    only exports tables defined in that YAML configuration file.

    Example:
        # Export all tables
        datamultiplier dump-all --db-url postgresql://user:pass@localhost/mydb \\
            --output-dir ./backups

        # Export only tables in schema.yaml
        datamultiplier dump-all --db-url postgresql://user:pass@localhost/mydb \\
            --config schema.yaml --output-dir ./backups
    """
    click.echo(f"Exporting tables from schema '{schema}'...")
    click.echo(f"  Output directory: {output_dir}")

    db = DatabaseConnection(db_url, schema=schema)
    db.connect()
    click.echo(f"✓ Connected")

    try:
        dumper = DataDumper(db)

        if config:
            # Dump only tables in config
            click.echo(f"Loading configuration from '{config}'...")
            config_obj = GenerationConfig.from_yaml(config)
            table_names = [table.name for table in config_obj.tables]
            click.echo(f"Dumping {len(table_names)} tables from config...")

            os.makedirs(output_dir, exist_ok=True)
            for table_name in table_names:
                output_path = os.path.join(output_dir, f"{table_name}.csv")
                dumper.dump_table_to_csv(table_name, output_path)
        else:
            # Dump all tables
            dumper.dump_all_tables_to_csv(output_dir)

        click.echo(f"✓ Export complete")

    finally:
        db.disconnect()


@main.command()
@click.option(
    "--csv-dir",
    type=click.Path(exists=True),
    required=True,
    help="Directory containing CSV files (from dump-all)",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    required=True,
    help="YAML configuration file (schema.yaml)",
)
@click.option(
    "--output",
    type=click.Path(),
    default="objects.jsonl",
    help="Output JSONL file path",
)
def objectify(csv_dir: str, config: str, output: str) -> None:
    """Convert CSV data to objects with relationship index.

    Reads CSV files and generates JSONL where each row is:
    {table, id, relates: {other_table: [ids]}}

    Example:
        datamultiplier dump-all --db-url ... --output-dir ./data
        datamultiplier objectify --csv-dir ./data --config schema.yaml --output objects.jsonl
    """
    click.echo(f"Loading configuration from '{config}'...")
    config_obj = GenerationConfig.from_yaml(config)

    click.echo(f"Building relationship index from CSV files in '{csv_dir}'...")
    indexer = RelationIndexer(csv_dir, config_obj)
    row_count = indexer.objectify(output)

    click.echo(f"✓ Wrote {row_count:,} objects to '{output}'")
    click.echo(f"\nNext: Use --group to cluster related objects:")
    click.echo(f"  datamultiplier group-objects --input {output} --output grouped.jsonl")


@main.command()
@click.option(
    "--db-url",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL connection URL",
)
@click.option(
    "--schema",
    default=None,
    help="Database schema name (default: user's search_path)",
)
@click.option(
    "--input",
    type=click.Path(exists=True),
    required=True,
    help="CSV file or directory of CSV files to load",
)
@click.option(
    "--table",
    default=None,
    help="Table name (only needed if --input is a single CSV file)",
)
@click.option(
    "--disable-fks",
    is_flag=True,
    help="Disable FK constraints before loading (saves to fk_constraints.json)",
)
@click.option(
    "--enable-fks",
    is_flag=True,
    help="Re-enable FK constraints after loading (from fk_constraints.json)",
)
@click.option(
    "--state-file",
    type=click.Path(),
    default="fk_constraints.json",
    help="State file for FK constraints",
)
@click.option(
    "--truncate",
    is_flag=True,
    help="Truncate tables before loading",
)
def load(
    db_url: str,
    schema: str,
    input: str,
    table: str,
    disable_fks: bool,
    enable_fks: bool,
    state_file: str,
    truncate: bool,
) -> None:
    """Load CSV file(s) into database.

    Can load a single CSV file or all CSV files in a directory.
    Optionally disable/enable FK constraints for faster loading.

    Examples:
        # Load single file
        datamultiplier load --db-url postgresql://... --input users.csv --table users

        # Load directory with FK disabled
        datamultiplier load --db-url postgresql://... --input ./data --disable-fks --enable-fks

        # Load directory only (constraints unchanged)
        datamultiplier load --db-url postgresql://... --input ./data
    """
    input_path = Path(input)
    is_file = input_path.is_file()
    is_dir = input_path.is_dir()

    if not is_file and not is_dir:
        click.echo(f"✗ Input is neither a file nor a directory: {input}")
        raise click.Abort()

    if is_file and not table:
        click.echo(f"✗ When loading a single CSV file, --table is required")
        raise click.Abort()

    click.echo(f"Connecting to database...")
    db = DatabaseConnection(db_url, schema=schema)
    db.connect()
    click.echo(f"✓ Connected")

    try:
        # Disable FKs if requested
        if disable_fks:
            click.echo(f"\nDisabling foreign keys...")
            disable_foreign_keys(db, state_file)

        # Load data
        click.echo(f"\nLoading data...")
        loader = DataLoader(db)

        def on_progress(msg: str) -> None:
            """Callback for progress messages."""
            click.echo(msg)

        if is_file:
            row_count = loader.load_file(input, table, truncate=truncate, on_progress=on_progress)
            click.echo(f"✓ Loaded {row_count:,} rows into '{table}'")
        else:
            results = loader.load_directory(
                input, respect_fk_order=not disable_fks, truncate=truncate, on_progress=on_progress
            )
            total_rows = sum(results.values())
            click.echo(f"\n✓ Loaded {len(results)} tables ({total_rows:,} rows total)")

        # Re-enable FKs if requested
        if enable_fks:
            click.echo(f"\nRe-enabling foreign keys...")
            enable_foreign_keys(db, state_file)

        click.echo(f"\n✓ Load complete")

    finally:
        db.disconnect()


@main.command()
@click.option(
    "--input",
    type=click.Path(exists=True),
    required=True,
    help="JSONL file from objectify",
)
@click.option(
    "--output",
    type=click.Path(),
    default="grouped.jsonl",
    help="Output grouped JSONL file path",
)
def group_objects(input: str, output: str) -> None:
    """Group related objects into connected components.

    Merges objects that are transitively related via foreign keys.

    Example:
        datamultiplier group-objects --input objects.jsonl --output grouped.jsonl
    """
    click.echo(f"Grouping related objects from '{input}'...")

    config = GenerationConfig()  # Minimal config for grouping
    indexer = RelationIndexer(".", config)  # csv_dir unused for grouping
    group_count = indexer.group_objects(input, output)

    click.echo(f"✓ Created {group_count:,} groups in '{output}'")


@main.command()
@click.option(
    "--db-url",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL connection URL",
)
@click.option(
    "--schema",
    default=None,
    help="Database schema name (default: user's search_path)",
)
@click.option(
    "--state-file",
    type=click.Path(),
    default="fk_constraints.json",
    help="File to store FK definitions for re-enabling",
)
def disable_fks(db_url: str, schema: str, state_file: str) -> None:
    """Disable all foreign key constraints in the schema.

    Saves constraint definitions to a state file for later re-enabling.
    This is useful for faster bulk data insertion.

    Example:
        datamultiplier disable-fks --db-url postgresql://user:pass@localhost/mydb
        datamultiplier generate --db-url ... --config schema.yaml
        datamultiplier enable-fks --db-url postgresql://user:pass@localhost/mydb
    """
    click.echo(f"Connecting to database...")
    db = DatabaseConnection(db_url, schema=schema)
    db.connect()
    click.echo(f"✓ Connected")

    try:
        click.echo(f"\nFetching foreign key definitions from schema '{schema}'...")
        fk_defs = disable_foreign_keys(db, state_file)

        click.echo(f"\n✓ Disabled {len(fk_defs)} foreign keys")
        click.echo(f"✓ Saved definitions to '{state_file}'")
        click.echo(f"\nNext: Run your generate/insert commands, then:")
        click.echo(f"  datamultiplier enable-fks --db-url {db_url} --schema {schema} --state-file {state_file}")

    finally:
        db.disconnect()


@main.command()
@click.option(
    "--db-url",
    required=True,
    envvar="DATABASE_URL",
    help="PostgreSQL connection URL",
)
@click.option(
    "--schema",
    default=None,
    help="Database schema name (default: user's search_path)",
)
@click.option(
    "--state-file",
    type=click.Path(exists=True),
    default="fk_constraints.json",
    help="State file from disable-fks command",
)
@click.option(
    "--not-valid",
    is_flag=True,
    help="Add constraints as NOT VALID then validate (faster for large tables)",
)
def enable_fks(db_url: str, schema: str, state_file: str, not_valid: bool) -> None:
    """Re-enable foreign key constraints.

    Reads constraint definitions from the state file created by disable-fks
    and adds them back. If data violates constraints, the command will fail.

    Example:
        datamultiplier enable-fks --db-url postgresql://user:pass@localhost/mydb
    """
    click.echo(f"Connecting to database...")
    db = DatabaseConnection(db_url, schema=schema)
    db.connect()
    click.echo(f"✓ Connected")

    try:
        enable_foreign_keys(db, state_file, not_valid=not_valid)
        click.echo(f"✓ Removed state file '{state_file}'")

    finally:
        db.disconnect()


if __name__ == "__main__":
    main()
