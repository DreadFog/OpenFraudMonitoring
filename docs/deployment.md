# Deployment

OpenFraudMonitoring can collect data in several deployment modes. The choice matters for cookie-based authentication detection: the browser only sends a site's cookies when the collection request is made to a host covered by those cookies.

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
    @ofm_collection path /ofm.js /api/initial /api/heartbeat /api/behavioral_event

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
2. Confirm that `/ofm.js`, `/api/initial`, `/api/heartbeat`, and `/api/behavioral_event` use the monitored hostname.
3. Inspect the `/api/initial` request and confirm that its request headers contain `Cookie` when an applicable cookie exists.
4. Confirm that the response is handled successfully and that the session appears in the OFM dashboard.
5. For reverse-proxy deployments, verify that the OFM backend receives the original monitored `Host` value.

Do not use an absolute `https://ofm...` URL in the injected script when cookie detection is required. Use `/ofm.js` and proxy the collection routes through the monitored domain.
