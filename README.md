# OpenFraudMonitoring

Self-hosted browser fingerprinting and fraud monitoring. One script tag → device fingerprints, behavioral signals, bot detection, live dashboard.

## Quick Start

```bash
cp .env.example .env   # edit if needed
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| Demo page | http://localhost:3000/demo |
| API | http://localhost:5000 |

## Integration

```html
<script src="http://your-server/fingerprint.js"></script>
```

For cross-origin collection, set `OFM_SERVER_URL` in `.env` before building.

## Configuration

All variables are in [`.env.example`](.env.example). Key ones:

| Variable | Purpose |
|----------|---------|
| `OFM_SERVER_URL` | Remote server URL for the client script (empty = same-origin) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `POSTGRES_PASSWORD` | Database password |

## Documentation

- [Architecture](docs/architecture.md) — system overview, data flow, folder structure
- [Rules](docs/rules.md) — how to create and manage detection rules
- [Filters](docs/filters.md) — how filtering works, schema fields, code mapping

## License

MIT
