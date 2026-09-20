# Configuration Guide

This guide documents all available options for specifying column values in `schema.yaml`.

## Overview

Each column in the schema can be configured with various options to control how data is generated:

```yaml
tables:
  table_name:
    row_count: 10000
    columns:
      column_name:
        type: varchar          # Required: database column type
        faker: name            # Optional: Faker rule
        values: [...]          # Optional: Specific list of values
        min: 10                # Optional: Minimum value (numeric)
        max: 100               # Optional: Maximum value (numeric)
        primary_key: true      # Optional: Mark as primary key
        foreign_key: table.id  # Optional: Foreign key reference
        nullable: true         # Optional: Allow NULL values
        unique: true           # Optional: Unique constraint
        auto_increment: true   # Optional: Auto-increment
```

## Column Configuration Options

### `type` (Required)
The PostgreSQL data type.
```yaml
type: varchar
type: integer
type: numeric
type: timestamp
type: boolean
type: text
```

### `faker` — Faker-based Generation
Generate realistic data using [Faker](https://github.com/joke2k/faker).

**Common Faker rules:**
```yaml
faker: name              # Random full name
faker: first_name       # Random first name
faker: last_name        # Random last name
faker: email            # Random email address
faker: phone_number     # Random phone number
faker: street_address   # Random street address
faker: city             # Random city name
faker: country          # Random country
faker: zipcode          # Random zipcode
faker: user_name        # Random username
faker: password         # Random password
faker: url              # Random URL
faker: date_time        # Random datetime
faker: date             # Random date
faker: time             # Random time
faker: text             # Random text paragraph
faker: word             # Random single word
faker: boolean          # Random true/false
```

### `values` — Specific List of Values
Choose randomly from a predefined list (enums, choices).

**Text values:**
```yaml
status:
  type: varchar
  values: ['active', 'inactive', 'pending', 'archived']

role:
  type: varchar
  values: ['admin', 'user', 'guest', 'moderator']

country:
  type: varchar
  values: ['DK', 'SE', 'NO', 'DE', 'FR', 'GB', 'NL']
```

**Numeric values:**
```yaml
rating:
  type: integer
  values: [1, 2, 3, 4, 5]

priority:
  type: integer
  values: [0, 1, 2]
```

### `min` & `max` — Numeric Ranges
Generate random numbers within a specified range.

**Integer values:**
```yaml
age:
  type: integer
  min: 18
  max: 120

quantity:
  type: integer
  min: 1
  max: 1000
```

**Decimal values:**
```yaml
price:
  type: numeric
  min: 9.99
  max: 9999.99

balance:
  type: numeric
  min: 0.00
  max: 1000000.00
```

## Priority of Generation Methods

When multiple options are specified, datamultiplier uses this priority:

1. **`values`** — Specific list of allowed values (highest priority)
2. **`min`/`max`** — Numeric range
3. **`faker`** — Faker-based generation
4. **Type-based default** — Default generation based on column type (lowest priority)

Example: If both `values` and `faker` are specified, `values` takes precedence.

## Constraints

```yaml
primary_key: true              # Mark as primary key
auto_increment: true           # Auto-increment (identity)
foreign_key: other_table.id    # Foreign key reference
unique: true                   # Unique constraint
nullable: true                 # Allow NULL values
default: 'some_value'          # Default value
```

## Complete Example

```yaml
seed: 42

tables:
  users:
    row_count: 10000
    columns:
      id:
        type: integer
        primary_key: true
        auto_increment: true
      
      name:
        type: varchar
        faker: name
      
      email:
        type: varchar
        faker: email
        unique: true
      
      age:
        type: integer
        min: 18
        max: 120
      
      status:
        type: varchar
        values: ['active', 'inactive', 'suspended']
      
      created_at:
        type: timestamp
        faker: date_time
      
      is_admin:
        type: boolean
        faker: boolean

  products:
    row_count: 5000
    columns:
      id:
        type: integer
        primary_key: true
        auto_increment: true
      
      name:
        type: varchar
        faker: word
      
      price:
        type: numeric
        min: 9.99
        max: 9999.99
      
      category:
        type: varchar
        values: ['Electronics', 'Clothing', 'Books', 'Home & Garden']
      
      stock:
        type: integer
        min: 0
        max: 10000

  orders:
    row_count: 100000
    columns:
      id:
        type: bigint
        primary_key: true
        auto_increment: true
      
      user_id:
        type: integer
        foreign_key: users.id
      
      product_id:
        type: integer
        foreign_key: products.id
      
      quantity:
        type: integer
        min: 1
        max: 100
      
      status:
        type: varchar
        values: ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
      
      created_at:
        type: timestamp
        faker: date_time
```

## Tips

- **Reproducibility**: Set `seed` at the top level to ensure consistent data across runs
- **Performance**: `values` is fastest (simple random choice), `faker` is slower (generates new data)
- **Foreign Keys**: Ensure parent tables are defined first in the schema
- **Unique Values**: For columns marked `unique: true`, generated data should have few duplicates
- **NULL Values**: Combine `nullable: true` with `faker` for occasional NULL values (requires custom faker logic)

## Troubleshooting

**"No parent records found"**
- Ensure parent table is listed before child table in schema
- Ensure parent table has been generated first

**"Ambiguous faker rule"**
- Use the exact faker method name (case-sensitive)
- See Faker documentation for available methods

**"Invalid range"**
- Ensure `min <= max`
- Ensure values match column type (e.g., numeric types for min/max)
