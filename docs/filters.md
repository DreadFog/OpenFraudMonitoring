# Filters

Filters let you narrow down the session list in the dashboard or via the API. They use the same condition format as [detection rules](rules.md).

## Using Filters

### In the Dashboard

The filter builder appears above the session table. Click **+ Add Filter** to add a condition:

1. **Field** — select from the dropdown (e.g. "Client IP", "User Agent")
2. **Operator** — depends on the field type (e.g. `=`, `contains`, `>`)
3. **Value** — type to search; the input shows autocomplete suggestions from existing data

Click **Apply** to filter the session list. Click **Clear** to reset.

### Via the API

Pass a `filters` query parameter as a JSON array:

```
GET /api/sessions?filters=[{"field":"client_ip","op":"eq","value":"192.168.1.1"}]
```

Multiple conditions are combined with AND logic.

## Schema Endpoint

```
GET /api/schema
```

Returns the list of all filterable fields with their types and available operators:

```json
[
  {
    "name": "client_ip",
    "label": "Client IP",
    "type": "string",
    "operators": [
      {"name": "eq", "label": "="},
      {"name": "neq", "label": "≠"},
      {"name": "contains", "label": "contains"},
      ...
    ]
  },
  ...
]
```

## Autocomplete Endpoint

```
GET /api/suggest?field=client_ip&q=192
```

Returns up to 20 distinct values from the database matching the search term. Used by the frontend filter builder for autocomplete.

For boolean fields, returns `["true", "false"]`. For number fields, returns `[]` (no autocomplete).

## Available Fields

### Session-level fields

These are stored directly on the `sessions` table.

| Field name | Label | Type | DB column |
|------------|-------|------|-----------|
| `client_ip` | Client IP | string | `sessions.client_ip` |
| `risk_score` | Risk Score | number | `sessions.risk_score` |
| `fsid` | Fingerprint ID (fsid) | string | `sessions.fsid` |

### Fingerprint-level fields

These are auto-generated from FPScanner's `types.ts` via `generate_schema.py`.
Denormalized columns on the `fingerprints` table, extracted from the decrypted FPScanner payload at ingestion time. When used as a filter on the session list, they are wrapped in an `EXISTS` subquery.

**Signal fields** (from `signals.*`): `automation_webdriver`, `device_cpu_count`, `device_screen_resolution_width`, `browser_user_agent`, `graphics_web_gl_vendor`, `locale_internationalization_timezone`, etc.

**Detection fields** (from `fastBotDetectionDetails.*`): `det_has_webdriver`, `det_has_cdp`, `det_has_playwright`, `det_has_selenium_property`, `det_has_bot_user_agent`, `det_has_gpu_mismatch`, etc.

**Top-level fields**: `fsid`, `fast_bot_detection`, `url`.

Run `GET /api/schema` for the full, current list of all filterable fields and their operators.

## Operators

### String operators

| Operator | SQL equivalent | Example |
|----------|---------------|---------|
| `eq` | `= 'value'` | Exact match |
| `neq` | `!= 'value'` | Not equal |
| `contains` | `ILIKE '%value%'` | Substring (case-insensitive) |
| `not_contains` | `NOT ILIKE '%value%'` | Does not contain |
| `starts_with` | `ILIKE 'value%'` | Starts with |
| `ends_with` | `ILIKE '%value'` | Ends with |

### Number operators

| Operator | Meaning |
|----------|---------|
| `eq` | Equal |
| `neq` | Not equal |
| `gt` | Greater than |
| `gte` | Greater or equal |
| `lt` | Less than |
| `lte` | Less or equal |

### Boolean operators

| Operator | Meaning |
|----------|---------|
| `eq` | Equal (`"true"` or `"false"` as string) |

## Code Mapping

### Where the schema is defined

The schema is defined in `services/schema.py` — the `SCHEMA_FIELDS` list. Each entry maps a filter field name to a model class and column:

```python
{"name": "client_ip", "label": "Client IP", "type": "string", "model": "Session", "column": "client_ip"}
```

### How filters are translated to SQL

`rules/engine.py` contains the query builder:

- `build_condition(field_meta, op, value)` — takes a single condition and returns a SQLAlchemy filter expression
- `build_session_query(filters, logic, base_query)` — takes a list of conditions, wraps fingerprint-level conditions in `EXISTS` subqueries, and combines everything with AND/OR

### How autocomplete works

`routes/filters.py` → `GET /api/suggest`:

1. Looks up the field in the schema registry
2. For string fields: `SELECT DISTINCT column FROM table WHERE column ILIKE '%q%' LIMIT 20`
3. For boolean fields: returns `["true", "false"]`
4. For number fields: returns `[]`

### Adding a new filterable field

1. Add the column to the appropriate model in `models/` (e.g. `models/fingerprint.py`)
2. If it's a fingerprint field, update `Fingerprint.extract_fields()` to populate it from the raw JSONB
3. Add an entry to `SCHEMA_FIELDS` in `services/schema.py`
4. Recreate the database (or run a migration)

The field will automatically appear in `GET /api/schema`, in the frontend filter builder, and be usable in rule conditions.
