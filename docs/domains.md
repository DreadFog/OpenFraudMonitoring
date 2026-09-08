# Monitored Domains

Monitored domains let an administrator describe each site that embeds `ofm.js`: which cookie proves a visitor is authenticated, and which form submission counts as an authentication attempt. Configuration is global (one entry per host) and can be exported/imported as JSON.

This is separate from [CORS allowed origins](../README.md), which only control which sites may embed the script. Domain configuration adds behavior on top of collection.

## Requirements

Cookie detection reads the `Cookie` header of the collection request. The browser only sends a site's cookies when the request is made to that site's own host, so the script **and** the collection endpoints must be reachable through the monitored domain. See [Deployment](deployment.md) for the Caddy reverse-proxy pattern.

| Deployment | Cookie test |
|---|---|
| Script + API on the monitored origin | Works, including `HttpOnly` cookies |
| Script + API reverse-proxied through the monitored host | Works, including `HttpOnly` cookies |
| Separate OFM hostname (`OFM_SERVER_URL=https://ofm.example.com`) | Never sees the monitored site's cookies |

## Configuration

Administration page → **Monitored domains**. Each entry has:

| Field | Meaning |
|---|---|
| `domain` | Host to match, normalized to lowercase without port (`shop.example.com`) |
| `auth_cookie_name` | Optional. If this cookie is present on a collection request, `session.authenticated` becomes `true` |
| `form_action` | Login form action. May be a path (`/admin/login`) or an absolute URL |
| `form_method` | Form method, default `post` |
| `form_field_names` | Field names that must all be present in the submitted form |
| `active` | Inactive entries are ignored |

### Choosing the right cookie

Pick a cookie that only exists **after** a successful login and is cleared **on logout** — typically the application's own session identifier (e.g. `sid`, `PHPSESSID`, `connect.sid`). Verify it in the browser's Network/Storage panel: log out, reload, and confirm the cookie disappears.

Avoid analytics/tracking cookies (RudderStack `rl_*`, Google Analytics `_ga*`, PostHog `ph_*`, etc.). These are set on every page load regardless of login state and never cleared on logout, so they will report `authenticated=true` even on the login page itself and after logging out. If `authenticated` is `true` on a login-page button click or auth-attempt event, that is the tell — the configured cookie is not an auth cookie.

### Matching rules

An `auth_attempt` event is created when **all** of the following match a `form_submit` event:

- The request host equals the configured `domain`.
- The method equals `form_method` (case-insensitive).
- The action matches `form_action`. A configured path such as `/admin/login` also matches the absolute URL the browser reports (`https://shop.example.com/admin/login`).
- Every configured field name is present in the submitted field names (subset match, case-insensitive). Extra fields such as CSRF tokens are allowed.

Matching is evaluated at ingestion time only. Changing a configuration does **not** re-scan existing events; submit the form again to test.

## Import / export

`Export JSON` downloads every configuration as `ofm-domains.json`. `Import JSON` accepts that file (or a bare array) and upserts by `domain`.

```json
{
  "version": 1,
  "domains": [
    {
      "domain": "shop.example.com",
      "auth_cookie_name": "session_id",
      "form_action": "/login",
      "form_method": "post",
      "form_field_names": ["email", "password"],
      "active": true
    }
  ]
}
```

## Session and event fields

- `authenticated` (boolean, session-level) — refreshed on every `/api/initial`, `/api/heartbeat`, and `/api/behavioral_event` from the configured cookie's presence. Filterable and usable in rules.
- `domains` (array) — normalized hosts of every URL seen in the session, subdomains preserved (`api.example.com` stays distinct from `example.com`). Filterable with `eq`/`contains`/`neq`/`not_contains`, supports autocomplete, and can be grouped in pie/histogram widgets.
- `authenticated` (boolean, per-record) — the same cookie-presence check, stamped independently onto every `Fingerprint`, `Heartbeat`, and typed behavioral event (including `AuthAttemptEvent`) at ingestion time. This is a request-time snapshot, not a continuous signal: the exact moment auth state changed between two events is not known, only that it changed somewhere in between. Historical rows recorded before this field existed default to `false` and are not backfilled.

Both session-level fields appear in the session overview of the session detail page. In the activity timeline, consecutive URL-boxes that are *fully* authenticated (every event inside them) are wrapped in a green-bordered "🔒 Authenticated" cluster — a cluster can span multiple boxes/pages, and a legend appears above the timeline only when at least one cluster exists. Heartbeat aggregation (the collapsed "N heartbeats" item) also breaks whenever the authenticated state changes, so a merged block never mixes states. A box with a mix of authenticated and non-authenticated events (rare — e.g. logging in mid-heartbeat-run on the same page) is simply left out of a cluster rather than split. Authentication attempts appear in the activity timeline as **🔐 Authentication attempt**.

## Troubleshooting

Set `LOG_LEVEL=DEBUG` and watch the backend:

```bash
docker compose logs -f backend | grep -E "auth cookie check|auth form check|authentication attempt detected"
```

- `auth cookie check … configured=False` — no active entry for that host, or the request did not reach OFM through the monitored host.
- `auth cookie check … cookie_present=False` — the cookie name does not match, or the cookie is not scoped to that host/path.
- `auth cookie check … cookie_present=True` on a login-page event (before any credentials were submitted) or after logging out — the configured cookie is not an auth cookie (see "Choosing the right cookie" above); it is likely an always-present analytics/tracking cookie.
- `auth form check … matched=False` — compare the logged `action`/`method` against the configuration; method and action mismatches are the common causes.
- `authentication attempt detected` — a match was stored in `beh_auth_attempt`.

Cookie values and form values are never logged.

## API

All endpoints require the `admin` role.

```
GET    /api/admin/domains
POST   /api/admin/domains
PUT    /api/admin/domains/<id>
DELETE /api/admin/domains/<id>
GET    /api/admin/domains/export
POST   /api/admin/domains/import
```

`auth_attempt` events are generated server-side only; posting that `event_type` to `/api/behavioral_event` returns `400`.
