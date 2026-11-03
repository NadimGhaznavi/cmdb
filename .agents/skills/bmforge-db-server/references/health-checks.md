---
title: Application Health Checks
lang: en
locale: en-US
language_name: English
translation_key: bmforge-health-checks
---

**One simple application-owned health interface for monitoring.** CMDB asks the application whether its required components can do their jobs; CMDB does **not** connect directly to MariaDB. A health check reports state. It must not restart processes, repair connections, retry operations, or invent monitoring infrastructure.

## What CMDB probes

For an application with an HTTP listener, use **GET `/health` on that existing listener**. No new port or server.

- Respond **HTTP 200** when all required, enabled components are usable.
- Respond **HTTP 503** when a known required component is unavailable. A timeout, unreachable service, or any other non-200 response is also **red** to the monitor.
- Return a small JSON body identifying component states, for example:

```json
{"status":"ok","components":{"http":"ok","zmq":"ok","db-server":"ok"}}
```

On a database failure:

```json
{"status":"error","components":{"http":"ok","zmq":"ok","db-server":"error"}}
```

Include only components that the application actually uses. Use `Content-Type: application/json` and `Cache-Control: no-store`. Do not reveal credentials, connection strings, or exception traces. Log the actionable failure on the application side. A `200` response must never contain an overall `error` status.

`/health` answers **application readiness**, not merely whether an HTTP socket accepts connections. A separate `/ready` endpoint is unnecessary unless another explicit integration requires it; if present, reuse the same check.

## What each component checks

| Component | Minimal check | How it is reached |
| --- | --- | --- |
| HTTP server | HTTP request is served, and the application can check its required components | `GET /health` |
| ZeroMQ server | Existing REQ/REP handler answers a `method: "health"` request with `status: "ok"` | Existing ZeroMQ endpoint; the application may call it when reporting aggregate health |
| DB Server | Application's own database layer makes one bounded, read-only query through its configured connection | Internal application method invoked by the application health handler; **not** a direct CMDB-to-MariaDB probe |

A ZeroMQ-only application may expose its health through its existing ZeroMQ protocol; **do not create an HTTP server solely for monitoring**. CMDB will need a compatible probe before it can monitor that endpoint. A non-running toolkit or standalone utility needs no network health endpoint.

A DB Server health check is an **application operation**. It must exercise the connection and permissions that the application actually uses, for example a `SELECT 1` via its DB manager. Checking that a MariaDB daemon happens to be running does not establish application database health. Do not open a special CMDB database connection or bypass application credentials.

## Failure and verification rules

Keep probes **on demand, read-only and bounded by the application's existing network/database timeouts**. No background polling, automatic recovery, generic circuit breaker, or new monitoring service. Use established configuration to locate listeners. Missing or failed required components report unhealthy; unused components are omitted, not failed.

Verify an application's normal probe returns `200`, that a required ZeroMQ or database failure makes it `503`, and that recovery restores `200`. Verify the component name appears in the failure response, no secrets leak, and no state is mutated.

This specifies what BMForge applications expose. **CMDB polling and dashboard colouring are future CMDB implementation work**, not included in this repository change.

---

[Back to BMForge]({{ site.baseurl }}{% link index.md %})
