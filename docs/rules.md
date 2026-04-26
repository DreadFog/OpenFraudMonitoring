# Detection Rules

Rules are conditions that automatically adjust a session's risk score when matched. They are evaluated asynchronously by the worker process.

## Default Rules

OFM ships with built-in rules stored as JSON files in [`backend/rules/defaults/`](../backend/rules/defaults/). They are loaded into the database automatically on startup (skipped if a rule with the same name already exists).

To add a new default rule, drop a `.json` file in that folder — it will be picked up on the next restart.

## Rule Syntax

A rule is a JSON object with the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique identifier (used as the flag name on matched sessions) |
| `description` | string | no | Human-readable explanation |
| `rule_type` | `"realtime"` or `"periodic"` | no (default `"realtime"`) | When the rule is evaluated |
| `logic` | `"AND"` or `"OR"` | no (default `"AND"`) | How conditions are combined |
| `conditions` | array | yes | List of condition objects |
| `score_modifier` | int | no (default `0`) | Points to add to the session's risk score on match |

Each **condition** is an object with three keys:

```json
{"field": "<schema_field>", "op": "<operator>", "value": "<value>"}
```

Available fields and operators are documented in [filters.md](filters.md).

### Example

This rule detects headless Chrome browsers and adds 30 points to the risk score:

```json
{
  "name": "HEADLESS_CHROME",
  "description": "Flags sessions using headless Chrome — no screen and WebDriver enabled",
  "rule_type": "realtime",
  "logic": "AND",
  "conditions": [
    {"field": "det_has_webdriver", "op": "eq", "value": "true"},
    {"field": "device_screen_resolution_width", "op": "eq", "value": "0"}
  ],
  "score_modifier": 30
}
```

When a session matches, the worker:
1. Creates a `RuleMatch` row (prevents duplicate matches)
2. Appends `"HEADLESS_CHROME"` to `session.flags`
3. Adds `30` to `session.risk_score` (capped at 100)

## Rule Types

- **Realtime** — evaluated immediately when a new fingerprint or heartbeat is ingested. The worker picks up the event from the Redis queue and tests only the triggering session against all realtime rules.

- **Periodic** — evaluated on a timer (default every 60 seconds). All sessions are tested against all periodic rules. Useful for rules that need a broader view (e.g. "more than 5 sessions from the same IP").

## API

### List rules

```
GET /api/rules
```

### Create a rule

```
POST /api/rules
Content-Type: application/json

{
  "name": "Headless Chrome Detector",
  "description": "Flags sessions using headless Chrome",
  "rule_type": "realtime",
  "logic": "AND",
  "conditions": [
    {"field": "browser_user_agent", "op": "contains", "value": "HeadlessChrome"}
  ],
  "score_modifier": 30,
  "enabled": true
}
```

### Update a rule

```
PUT /api/rules/<id>
Content-Type: application/json

{
  "enabled": false
}
```

Only the fields you include are updated.

### Delete a rule

```
DELETE /api/rules/<id>
```

This also removes all associated `RuleMatch` rows.

## Examples

### Detect automated browsers

```json
{
  "name": "WebDriver bot",
  "rule_type": "realtime",
  "logic": "OR",
  "conditions": [
    {"field": "det_has_webdriver", "op": "eq", "value": "true"},
    {"field": "browser_user_agent", "op": "contains", "value": "HeadlessChrome"}
  ],
  "score_modifier": 40
}
```

### Flag sessions from a specific IP

```json
{
  "name": "Suspicious IP",
  "rule_type": "realtime",
  "logic": "AND",
  "conditions": [
    {"field": "client_ip", "op": "eq", "value": "203.0.113.42"}
  ],
  "score_modifier": 50
}
```

### Low-resource device (possible emulator)

```json
{
  "name": "Emulator fingerprint",
  "rule_type": "realtime",
  "logic": "AND",
  "conditions": [
    {"field": "device_cpu_count", "op": "lte", "value": "1"},
    {"field": "device_memory", "op": "lte", "value": "1"},
    {"field": "device_screen_resolution_width", "op": "eq", "value": "0"}
  ],
  "score_modifier": 25
}
```

### Periodic: flag sessions with a known bad platform

```json
{
  "name": "Linux desktop — review",
  "rule_type": "periodic",
  "logic": "AND",
  "conditions": [
    {"field": "device_platform", "op": "eq", "value": "Linux x86_64"}
  ],
  "score_modifier": 5
}
```

## How It Works Internally

1. `routes/collect.py` and `routes/heartbeat.py` push `{"session_id": <int>, "type": "fingerprint"|"heartbeat"}` to the Redis list `ofm:events`.

2. `worker.py` runs `BRPOP` on `ofm:events`. For each event, it loads all enabled realtime rules and calls `rules/engine.py → evaluate_rule(rule, session_id)`.

3. `evaluate_rule` calls `build_session_query(rule.conditions, rule.logic)` which translates each condition into a SQLAlchemy filter. Fingerprint-level conditions are wrapped in `EXISTS` subqueries.

4. If the session matches, a `RuleMatch` row is inserted (prevents duplicate matches), the rule's `name` is appended to `session.flags`, and `session.risk_score` is increased (capped at 100).

### Code path

```
app.py / worker.py
  └─ seed_default_rules()                          # rules/__init__.py
       └─ load_default_rules()                     #   reads rules/defaults/*.json
       └─ INSERT INTO rules … (skip if name exists)

routes/collect.py
  └─ enqueue_event(session_id, "fingerprint")      # services/event_queue.py

worker.py
  └─ process_realtime_events()
       └─ _apply_rule_matches(rules, session_id)
            └─ evaluate_rule(rule, session_id)      # rules/engine.py
                 └─ build_session_query(conditions)
                      └─ build_condition(meta, op, value)
```
