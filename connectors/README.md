# Connectors

Each subdirectory under `connectors/` is an independent connector container
that talks to the OpenFraudMonitoring backend through RabbitMQ.

For full documentation on how connectors work, configuration, and how to build your own, see [docs/connectors.md](../docs/connectors.md).

## Architecture

```
backend  ──publish──>  ofm.intel exchange  ──route──>  intel.requests.<connector>
                                                           │
                                                           ▼
                                                      connector
                                                           │
backend worker  <──consume──  intel.responses  <──publish──┘
```

Connectors also write a heartbeat key to Redis every 10 s
(`ofm:connector:<name>:heartbeat`) which the `/logging` page uses for
liveness display.

## Shared library

`connectors/base/` provides `connector_base` — a Python package with:
- `load_config(path)` — YAML config loader with environment-backed defaults
- `ConnectorRunner(config, handler)` — RabbitMQ consume/publish loop + Redis heartbeat
- `log_shipper` — centralized log shipping to Redis

## Available connectors

| Connector | Scope | Mode | Description |
|-----------|-------|------|-------------|
| `ipinfo` | `ipv4-addr`, `ipv6-addr` | auto | IPinfo Lite API — AS number + country |
| `opencti` | `ipv4-addr`, `ipv6-addr`, `user-agent` | manual | OpenCTI — indicators, malware, campaigns |
