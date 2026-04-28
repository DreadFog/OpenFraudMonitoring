# Connectors

Each subdirectory under `connectors/` is an independent connector container
that talks to the OpenFraudMonitoring backend through RabbitMQ.

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
- `load_config(path)` — YAML config loader
- `ConnectorRunner(config, handler)` — RabbitMQ consume/publish loop
- `BackendClient(base_url, token)` — fallback HTTP client to the backend

## Available connectors

- `connectors/opencti/` — queries an OpenCTI instance (added in Phase 3)
