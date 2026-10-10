# Deployment

OpenFraudMonitoring can collect data in several deployment modes. The choice matters for cookie-based authentication detection: the browser only sends a site's cookies when the collection request is made to a host covered by those cookies.

## Visitor notice

Loading `ofm.js` displays a bottom-of-page notice: "This website protects itself against fraud attempts using OpenFraudMonitoring. For this purpose, data about your web browser and activity on this site will be collected." The project name links to [the GitHub repository](https://github.com/DreadFog/OpenFraudMonitoring).

The **OK** button dismisses the notice and sets `ofm_notice_acknowledged=1` on the monitored page's host, not the script server's host. The cookie has `Path=/`, `Max-Age=31536000` (one year), `SameSite=Lax`, and `Secure` on HTTPS. It contains only the acknowledgment flag, is readable by client JavaScript, and is unrelated to the monitored site's authentication cookie. Removing it or allowing it to expire makes the notice appear again. If cookies are unavailable, dismissal still works for the current page but may not persist.

The banner is informational: **OK is not a consent gate**, and fingerprint/behavior collection is not delayed or disabled by the notice. Site operators remain responsible for any required consent mechanism and privacy disclosures. Rebuild the client/backend image and refresh cached copies of `ofm.js` to deploy the notice.

## Server location and latency measurements

Administrators configure **Administration > Server** (`/admin/server`). The
location has a descriptive name and optional latitude/longitude; coordinates
must be provided together and be within -90..90 and -180..180 respectively.
The timezone is a validated IANA identifier, such as `Europe/Paris`; the default
is `UTC`. These are global settings (`server.location`, `server.timezone`), not
changes to the operating system's timezone. Location is intentionally unset by
default; no geolocation lookup is performed.

The client `latency` extension measures `GET /api/latency`, a public endpoint
returning an empty `204` response. The endpoint performs no database queries,
session writes, rule evaluation, or Redis calls. Its public wildcard CORS avoids
the database-backed origin lookup used for credentialed collection requests.
Both server response headers and client fetch options prevent caching; the
client verifies the response status and `X-OFM-Latency-Probe: 1` marker.

Each measurement uses **two sequential requests**: a discarded warm-up followed
by a timed probe using `performance.now()`, stopping at response headers. Probes
omit credentials and have a 5-second timeout per request. Concurrent refreshes
share one in-flight pair. This reduces connection-setup effects and excludes
ingestion database/queue work. Network delay, proxy/worker scheduling, and browser
scheduling can still contribute; it is not one-way latency or proof of distance.

Initial fingerprint collection waits for its probe pair, so the initial payload
can already include a sample. Each visible heartbeat starts a background refresh
and sends the previous sample; the refreshed sample travels with the next normal
request. Hidden pages skip probes. Failed/aborted requests, incorrect status or
marker responses, and probes completed after the page becomes hidden do not
replace the last valid sample. If no probe has succeeded, the sample is `null`.

Initial, heartbeat, and behavioral requests carry the latest sample as
`extensions.latency` but **never measure their own ingestion time**. Normal
collection still uses credentialed fetch with a 15-second timeout. Hidden-page
delivery uses `sendBeacon` when available, with fetch fallback if rejected.

Example client sample:

```json
{
    "round_trip_ms": 42.125,
    "measured_at": 1791200000000,
    "request_path": "/api/latency",
    "measurement": "lightweight_probe",
    "client_timezone": "Europe/Paris",
    "client_utc_offset_minutes": 120
}
```

`measured_at` is the client's Unix timestamp in milliseconds; the UTC offset is
positive east of UTC. Query strings are omitted from `request_path`. The browser
timezone is an advertised JavaScript value, not a verified location or a custom
HTTP header. Samples are untrusted: the backend ignores malformed values and
marks accepted samples `source: "client_reported"`, adding `received_at` and the
server configuration at ingestion time. New probe samples are labeled
`measurement: "lightweight_probe"`; older ingestion timings retain
`measurement: "fetch_response_headers"`. The `latency_ms` filter continues to
use the session's latest sample; historical timings are not rewritten.
Client-supplied server metadata is not trusted.

The latest sample is stored on the session and exposed by its detail API.
Heartbeats retain per-request samples in their `latency` field and summaries;
initial fingerprints retain the normalized sample under `_extensions.latency`.
Behavioral requests update the session's latest sample. Session retention removes
these samples along with their owning records.

The timezone/latency matching connector, mismatch detection, and risk scoring are
**not implemented**. VPNs, proxies, network congestion, and server load can all
affect timing independently of the advertised timezone.

Deploy the client, backend, frontend, and worker images together:

```bash
docker compose up -d --build backend frontend worker
```

Backend/worker startup adds nullable JSONB `latency` columns to existing session
and heartbeat tables through the existing idempotent schema-upgrade mechanism.
Ensure monitored sites refresh cached copies of `ofm.js`.
Reverse proxies serving selected collection paths must forward `/api/latency`
to the same backend too; otherwise probe marker verification fails and no new
samples are recorded.

Client transport regression tests run with `npm test` in the `client` directory
(Node 18+). Backend configuration/ingestion checks are in
`backend/tests/test_latency.py`.

## Data management

Administrators configure **Administration > Data management** (`/admin/retention`).
The default is **6 calendar months** of inactivity; the setting accepts positive
whole numbers of months and is stored as the global key `data.retention_months`.

Indicator revocation defaults to **7 days** without enrichment, configured by
`intel.indicator_revocation_days` (positive whole days). Only indicators have a
platform `revoked` state. Saving a new delay recalculates it immediately; reads
and the hourly worker also keep it current. Fresh, unrevoked enrichment resets
age-based revocation, but source-provided revocation always takes precedence.
This policy does not delete indicators and is independent of retention.

The worker runs cleanup on startup and once per hour, reading the current setting
each time. A session expires when its `last_seen` is strictly before the UTC
cutoff. Calendar-month subtraction clamps month-end dates to the last valid day
of the target month. Activity timestamps are stored in JavaScript milliseconds.

Deleting a session cascades through fingerprints, heartbeats, URLs, browser
session records, rule matches, and every typed behavioral-event table. Devices
and their cookie aliases are deleted when no retained sessions remain. A retained
device's `last_seen` is recomputed from its associated sessions; its recent IP
list is rebuilt from retained sessions so expired IP values are not left there.

IPv4, IPv6, user-agent observables, and related intelligence remain while needed
by retained sessions. Expired sessions' exclusive observables and enrichment are
removed, including relationships to deleted entities; sharing an autonomous
system or country does not keep an inactive IP alive. Standalone intelligence
without session references uses its last refresh time (or creation time if never
refreshed) for expiry. Configuration, rules, dashboards, and user accounts are
not subject to visit-data retention.

**Deletion is permanent.** Deploying the updated worker starts the first sweep
immediately. To change the default before that sweep, deploy the backend and
frontend first, save the desired policy, then deploy the worker. Shortening the
policy applies to existing data at the next sweep; increasing it cannot restore
deleted data. Backups and external connector/queue storage need their own
retention policies. No database column migration is needed for this feature.

Rebuild and deploy the changed services:

```bash
docker compose up -d --build backend frontend worker
```

### Retention regression tests

Tests requiring PostgreSQL are enabled by `RETENTION_TEST_DATABASE_URL`. Point
this variable only at a disposable database: the integration tests create and
drop the entire schema. Without it, the calendar and validator unit tests run,
and database integration tests are skipped.

```bash
cd backend
RETENTION_TEST_DATABASE_URL=postgresql://test:test@localhost/ofm_test \
    python -m unittest discover -s tests -p test_retention.py -v
```

## Shared Docker network for a reverse proxy

The Compose file uses an external Docker network named `internal_network`. Its purpose is to let a reverse proxy such as Caddy, managed by a separate Compose project, communicate with the OFM containers without publishing the frontend port on the host.

Create the network once before starting OpenFraudMonitoring:

```bash
docker network create internal_network
```

The Caddy and OFM Compose projects must both attach their services to this network. Caddy can then use Docker service or container names as upstreams, for example:

```caddy
reverse_proxy ofm-frontend:3000
```

The OFM frontend exposes port `3000` only inside the Docker network. The backend remains reachable by its internal name, `backend:5000`, for services that need to communicate with it. Because `internal_network` is declared as external, Docker Compose does not create it automatically and startup fails if the network does not already exist.

## Deployment modes

### 1. Same-origin deployment

Serve the client script and the collection API from the monitored site's origin. This is the simplest mode for cookie detection.

```html
<script src="/ofm.js"></script>
```

The client sends requests to relative paths such as `/api/initial`. The browser automatically includes cookies for that origin, including cookies marked `HttpOnly`. The backend can inspect them from the request's `Cookie` header.

Use an empty `OFM_SERVER_URL` when building the client:

```env
OFM_SERVER_URL=
```

### 2. Reverse-proxied deployment per monitored domain (recommended)

When the OFM backend runs separately, proxy the OFM script and collection endpoints through each monitored domain. The page still uses a relative script URL, so all collection requests remain same-origin:

```caddy
(inject_ofm) {
    replace `</body>` `<script src="/ofm.js"></script></body>`
}

(ofm_routes) {
    @ofm_collection path /ofm.js /api/initial /api/heartbeat /api/behavioral_event /api/latency

    handle @ofm_collection {
        reverse_proxy ofm:5000 {
            header_up Host {http.request.host}
        }
    }
}

portainer.example.com {
    import inject_ofm

    route {
        import ofm_routes

        handle {
            reverse_proxy portainer:9000 {
                header_up Accept-Encoding identity
            }
        }
    }
}
```

For a second monitored site, reuse the same `ofm_routes` snippet and change only the fallback upstream:

```caddy
home.example.com {
    import inject_ofm

    route {
        import ofm_routes

        handle {
            reverse_proxy http {
                header_up Accept-Encoding identity
            }
        }
    }
}
```

The OFM backend receives the original monitored host through the `Host` header. The domain configuration can therefore select the correct cookie and form-matching rules for each host.

The Caddy service must be able to resolve `ofm:5000`. If Caddy runs outside the Docker network, use the backend's reachable address instead, such as `127.0.0.1:5000`.

The `ofm_routes` matcher should include every client collection endpoint used by the build. The current collection endpoints are:

- `/ofm.js`
- `/api/initial`
- `/api/heartbeat`
- `/api/behavioral_event`
- `/api/latency` (GET, lightweight probe)

Keep the OFM handles before the application's fallback proxy. Otherwise the application container may receive `/api/initial` instead of the OFM backend.

### 3. Separate OFM hostname

This mode uses an absolute script URL such as:

```html
<script src="https://ofm.example.com/ofm.js"></script>
```

Set the client URL at build time:

```env
OFM_SERVER_URL=https://ofm.example.com
```

This mode can collect fingerprints and behavioral events when CORS is configured, but it cannot reliably test cookies belonging to `shop.example.com`. Requests to `ofm.example.com` do not receive cookies scoped to `shop.example.com`, even when the request uses credentials. CORS controls whether a response may be read; it does not transfer cookies between unrelated domains.

Use this mode only when cookie-based authentication detection is not required, or when the monitored application explicitly provides authentication state through another integration mechanism.

## Cookie-based authentication tests

The domain configuration lets an administrator associate a monitored host with an optional cookie name. During collection, the backend checks the incoming request's cookies and sets the session's `authenticated` value according to the configured cookie's presence. See [Monitored Domains](domains.md) for the configuration fields, login-form matching, and JSON import/export.

| Deployment | Cookie test result |
|---|---|
| Script and API same-origin | Works, including `HttpOnly` cookies |
| Script served through monitored host and API reverse-proxied there | Works, including `HttpOnly` cookies |
| Script on a separate OFM hostname | Does not see the monitored site's cookies |
| Client-side `document.cookie` workaround | Sees only non-`HttpOnly` cookies and is not the preferred deployment |

A cookie must also be scoped so that the browser sends it to the monitored host. A cookie scoped to a different host, path, or incompatible security context will not be present in the request.

## CORS and credentials

Same-origin collection does not require a cross-origin CORS request. The client should use relative collection paths in this mode, which is achieved with an empty `OFM_SERVER_URL`.

If a separate-host deployment is used, configure an explicit allowed origin in OFM and use credentials where required. This still does not make cookies from the monitored host available to the OFM host; it only permits cross-origin request/response handling.

## Verifying a deployment

1. Open the monitored site and inspect the Network panel.
2. Confirm that `/ofm.js`, `/api/initial`, `/api/heartbeat`, `/api/behavioral_event`, and `/api/latency` use the monitored hostname. The probe must return `204` with `X-OFM-Latency-Probe: 1`.
3. Inspect the `/api/initial` request and confirm that its request headers contain `Cookie` when an applicable cookie exists.
4. Confirm that the response is handled successfully and that the session appears in the OFM dashboard.
5. For reverse-proxy deployments, verify that the OFM backend receives the original monitored `Host` value.

Do not use an absolute `https://ofm...` URL in the injected script when cookie detection is required. Use `/ofm.js` and proxy the collection routes through the monitored domain.
