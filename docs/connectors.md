# Connectors

Connectors are standalone Python services that enrich STIX observables with external threat intelligence. They communicate with the backend through RabbitMQ and publish their results as STIX 2.1 bundles.

## Architecture

```
Backend  ──publish──▶  ofm.intel exchange  ──route──▶  intel.requests.<name>
                                                            │
                                                       connector handler
                                                            │
Worker   ◀──consume──  intel.responses     ◀──publish──────┘
   │
   └──▶ ingest STIX bundle into PostgreSQL
```

Each connector:
1. Declares its own request queue `intel.requests.<name>` on the `ofm.intel` exchange
2. Consumes enrichment requests (e.g. "look up IP 1.2.3.4")
3. Calls an external API (IPinfo, OpenCTI, etc.)
4. Builds a STIX 2.1 bundle with the results
5. Publishes the bundle to the `intel.responses` queue
6. The backend worker ingests the bundle into per-type PostgreSQL tables

Connectors also publish metadata to Redis for observability:

| Redis key | Content |
|-----------|---------|
| `ofm:connector:<name>:heartbeat` | Unix timestamp, TTL 30s |
| `ofm:connector:<name>:mode` | `manual`, `auto`, or `both` |
| `ofm:connector:<name>:type` | Connector type (e.g. `enricher`) |
| `ofm:connector:<name>:scope` | JSON array of STIX entity types (e.g. `["ipv4-addr", "ipv6-addr"]`) |

## Configuration

Each connector has a `config.yml` file with the following structure:

```yaml
# Required
name: my-connector           # Unique connector name (used for queue routing)
mode: manual                 # manual | auto | both

# Connector metadata
connector_type: enricher     # enricher | importer
scope:                       # STIX entity types this connector can handle
  - ipv4-addr
  - ipv6-addr

# Infrastructure (defaults work inside Docker)
rabbitmq_url: amqp://ofm:ofm@rabbitmq:5672/
backend_url: http://backend:5000
connector_token: ""

# Connector-specific parameters (anything else is promoted to params)
my_api_token: "abc123"
```

All fields except `name` have defaults. Any top-level key not in the structural set (`name`, `mode`, `connector_type`, `scope`, `rabbitmq_url`, `backend_url`, `connector_token`, `params`) is automatically promoted into `config.params` for the connector handler to use.

Environment variables override YAML values:
- `RABBITMQ_URL` overrides `rabbitmq_url`
- `BACKEND_URL` overrides `backend_url`
- `CONNECTOR_TOKEN` overrides `connector_token`

## Trigger Modes

| Mode | Behavior |
|------|----------|
| `manual` | Only triggered from the Intelligence page via the "Enrich" button |
| `auto` | Automatically triggered when a new fingerprint is collected (for matching entity types) |
| `both` | Both automatic and manual triggering |

When the mode is `auto` or `both`, the backend scans Redis on each fingerprint collection to find connectors that support the observable type and publishes enrichment requests automatically.

## Available Connectors

### IPinfo (`connectors/ipinfo/`)

Queries the [IPinfo Lite API](https://ipinfo.io) to enrich IP addresses with geolocation and AS data.

**Scope:** `ipv4-addr`, `ipv6-addr`

**STIX output:**
- IP observable (ipv4-addr or ipv6-addr SCO)
- Autonomous System (autonomous-system SCO) with `belongs-to` relationship
- Country (location SDO) with `located-at` relationship

**Config:**
```yaml
name: ipinfo
mode: auto
connector_type: enricher
scope:
  - ipv4-addr
  - ipv6-addr
ipinfo_token: "your-token-here"
```

### OpenCTI (`connectors/opencti/`)

Queries an [OpenCTI](https://filigran.io/solutions/products/opencti-threat-intelligence-platform/) instance for threat intelligence on IPs and user agents.

**Scope:** `ipv4-addr`, `ipv6-addr`, `user-agent`

**STIX output:** Indicators, malware, campaigns, intrusion sets, and their relationships to the queried observable.

**Config:**
```yaml
name: opencti
mode: manual
connector_type: enricher
scope:
  - ipv4-addr
  - ipv6-addr
  - user-agent
opencti_url: "https://your-opencti-instance.example.com"
opencti_token: "your-api-token"
ssl_verify: true
```

## Building a Custom Connector

A connector is a Python script that uses the shared `connector_base` library. Here's the minimal structure:

### 1. Create the directory

```
connectors/my-connector/
  config.yml
  config.example.yml
  main.py
  my_client.py
  requirements.txt
  Dockerfile
```

### 2. Write the handler

```python
# main.py
import os, sys, logging
sys.path.insert(0, "/connectors/base")

from connector_base import load_config, ConnectorRunner
from connector_base.log_shipper import install as install_log_shipper
from my_client import MyClient

logging.basicConfig(level=logging.INFO)
install_log_shipper("connector:my-connector")


def main():
    cfg = load_config(os.environ.get("CONNECTOR_CONFIG", "/connectors/my-connector/config.yml"))
    client = MyClient(cfg.params.get("api_key"))

    def handler(msg: dict) -> dict:
        value = (msg.get("value") or "").strip()
        request_type = msg.get("type", "ip_lookup")
        if not value:
            return {"type": "bundle", "objects": []}
        return client.lookup(value)

    runner = ConnectorRunner(cfg, handler)
    runner.run()


if __name__ == "__main__":
    main()
```

The `handler` function receives a request message and must return a STIX 2.1 bundle dict:

```python
{
    "type": "bundle",
    "id": "bundle--<uuid>",
    "objects": [
        # STIX SCOs (observables) and SDOs
        {"type": "ipv4-addr", "id": "ipv4-addr--<uuid>", "value": "1.2.3.4"},
        {"type": "autonomous-system", "id": "autonomous-system--<uuid>", "number": 13335, "name": "CLOUDFLARENET"},
        # STIX SROs (relationships)
        {"type": "relationship", "id": "relationship--<uuid>",
         "relationship_type": "belongs-to",
         "source_ref": "ipv4-addr--<uuid>",
         "target_ref": "autonomous-system--<uuid>"}
    ]
}
```

### 3. Create the Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /connectors

COPY connectors/base/ /connectors/base/
RUN pip install --no-cache-dir -r /connectors/base/requirements.txt

COPY connectors/my-connector/ /connectors/my-connector/
RUN pip install --no-cache-dir -r /connectors/my-connector/requirements.txt

CMD ["python", "/connectors/my-connector/main.py"]
```

### 4. Add to docker-compose.yml

```yaml
connector-my-connector:
  build:
    context: .
    dockerfile: connectors/my-connector/Dockerfile
  environment:
    LOG_LEVEL: ${LOG_LEVEL:-INFO}
    RABBITMQ_URL: ${RABBITMQ_URL:-amqp://ofm:ofm@rabbitmq:5672/}
    REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
    BACKEND_URL: ${BACKEND_URL:-http://backend:5000}
    CONNECTOR_TOKEN: ${CONNECTOR_TOKEN:-dev-connector-token}
    CONNECTOR_CONFIG: /connectors/my-connector/config.yml
  volumes:
    - ./connectors/my-connector/config.yml:/connectors/my-connector/config.yml:ro
  depends_on:
    rabbitmq:
      condition: service_healthy
    redis:
      condition: service_healthy
```

### 5. Create config.yml

```yaml
name: my-connector
mode: manual
connector_type: enricher
scope:
  - ipv4-addr
api_key: "your-api-key"
```

Once deployed, the connector will appear automatically in the Logging page and the Intelligence page's "Enrich" dropdown (filtered by scope).

## Request Message Format

The connector receives messages with this structure:

```json
{
    "request_id": "uuid-string",
    "type": "ip_lookup",
    "value": "1.2.3.4",
    "connector": "my-connector"
}
```

## Response Message Format

The connector runner automatically wraps the handler's return value:

```json
{
    "request_id": "uuid-string",
    "connector": "my-connector",
    "value": "1.2.3.4",
    "ok": true,
    "error": null,
    "stix_bundle": { "type": "bundle", "objects": [...] }
}
```

If the handler raises an exception, `ok` is set to `false` and `error` contains the error message. The bundle will be empty.

## Supported STIX Types

The backend can ingest these STIX object types from connector bundles:

| STIX type | PostgreSQL table | Description |
|-----------|-----------------|-------------|
| `ipv4-addr` | `stix_ipv4_addr` | IPv4 address observable |
| `ipv6-addr` | `stix_ipv6_addr` | IPv6 address observable |
| `user-agent` | `stix_user_agent` | User-agent string observable |
| `autonomous-system` | `stix_autonomous_system` | AS number observable |
| `location` | `stix_country` | Country location SDO |
| `indicator` | `stix_indicator` | Threat indicator SDO |
| `malware` | `stix_malware` | Malware SDO |
| `campaign` | `stix_campaign` | Campaign SDO |
| `intrusion-set` | `stix_intrusion_set` | Intrusion set SDO |
| `relationship` | `stix_relationship` | Relationship SRO |
