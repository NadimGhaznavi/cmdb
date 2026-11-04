---
title: HTTP Display Server Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.http-server"
spec_version: "0.5.1"
spec_status: "draft"
translation_key: bmforge-component-http
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

This contract follows the [engineering policy]({{ site.baseurl }}{% link pages/engineering-contract.md %}), [health check contract]({{ site.baseurl }}{% link pages/health-checks.md %}), and [traceability rules]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

## Intent and scope

Provide a small, locally owned HTTP service using Python's `ThreadingHTTPServer`, `BaseHTTPRequestHandler`, and (when HTML is needed) Jinja2 templates with autoescaping. Do not introduce Flask, FastAPI, a frontend build, authentication framework, or extra infrastructure unless required by the consumer.

## Approved runtime modules

This is the **complete approved module inventory for the reusable HTTP Display Server infrastructure** in specification `0.5.1`.

| Origin | Module | Purpose |
| --- | --- | --- |
| Python stdlib | `argparse` | CLI host and port options |
| Python stdlib | `datetime` | Timezone-aware local date/time conversion and display formatting |
| Python stdlib | `http.server` | `ThreadingHTTPServer`, `BaseHTTPRequestHandler` and HTTP lifecycle |
| Python stdlib | `ipaddress` | Validate the configured IPv4 bind address |
| Python stdlib | `json` | JSON requests and the `/health` response |
| Python stdlib | `logging` | Report actionable request or lifecycle failures |
| Python stdlib | `pathlib` | Resolve templates and static assets |
| Python stdlib | `signal` | SIGTERM shutdown handling |
| Python stdlib | `urllib.parse` | URL and query-string parsing |
| Python stdlib | `zoneinfo` | Apply an explicitly configured IANA local timezone when required |
| Third-party | `jinja2` | `Environment`, `FileSystemLoader`, `StrictUndefined`, `select_autoescape` for server-rendered HTML |

**Approval boundary:** This list is binding for the reusable component infrastructure. Codex may rename local classes, configure ports and paths, and implement the application-owned handlers, but **must pause and ask the user** before adding, removing, or replacing an approved module or framework. Do not install another package as a workaround. User-approved changes belong in a revised BMForge specification before adoption.

These are Python import modules, not a complete transitive dependency tree. The consuming application's dependency file records installed package versions. Application business logic and separately selected BMForge components are outside this list; they must not quietly change this component's technology choices.

**Not part of this component:** PyMySQL imports in the BMGeoIP HTTP handler belong to the GeoIP application's database operations, not HTTP transport. Plotly.js, Leaflet and Cytoscape.js are *optional browser presentation capabilities* specified separately in [Display Visualizations]({{ site.baseurl }}{% link pages/component-visualization.md %}), never implicit HTTP dependencies. Select only those the application actually needs. Do not replace this implementation with Django, Flask, FastAPI, Werkzeug, Gunicorn, NGINX, or another server framework without user approval.

## GUI design contract (human-facing HTML only)

When an HTTP application provides a browser GUI, **use a dark, high-contrast visual style inspired by BMDynIP**. This is a presentation standard; an API-only service needs no GUI. It does not change the approved HTTP transport modules.

**The implementing AI chooses the actual palette.** BMDynIP demonstrates the design language, not mandatory hex values or a specific combination of navy, cyan and orange.

- **Dark foundation:** Start with deep neutral or dark-hued backgrounds, distinct content panels and input surfaces, discernible borders, bright foreground text, and readable secondary labels.
- **Strong primary accents:** Choose saturated primary hues and adjacent vivid shades for links, primary buttons, focus and meaningful status. **Avoid pastels**, washed-out colors and low-contrast gray-on-gray themes. Apply accents consistently and sparingly rather than turning the page into neon.
- **Reusable tokens:** Keep the application's palette in CSS custom properties for background, surfaces, borders, text, muted text, links, actions, focus and status colors as needed. Maintain that palette throughout the app and any requested charts. The AI may use any dark palette that meets these rules.
- **Practical structure:** Take BMDynIP's clear masthead, hierarchy, bordered panels, readable tables, labeled forms, button states, status feedback, and confirmation controls as a visual guide. Only create components the requested workflow requires; do not reproduce BMDynIP's DNS settings, branding, icon, content or exact layout.
- **Accessible contrast and states:** Target WCAG AA **4.5:1** contrast for normal text, **3:1** for large text and **3:1** for essential control and focus indicators. Provide visible keyboard focus and legible hover, error, warning, success and disabled states. Status must not rely on color alone.
- **Responsive layout:** Ensure usable desktop and narrow/mobile views. Stack panels at small widths, retain accessible actions and scroll wide tables within their own containers, not the entire page.
- **Simple frontend:** Prefer app-owned HTML, CSS and ordinary browser JavaScript. Do not introduce Bootstrap, Tailwind, React, theme engines or other dependencies just to satisfy the visual style; a separately selected visualization component still governs charts and maps.

The pinned BMDynIP HTML and CSS are **design references only**. Inspect their variables, spacing, table scroll behavior, focus, buttons and media queries, then build the application's own interface. Never import assets directly from the BMDynIP runtime.

## Date and time display

- Display human-facing timestamps in **local time**, using the application's configured local timezone or, by default, the server's operating-system local timezone. Browser-rendered values must use the same timezone as server-rendered values; do not silently substitute the visitor's browser timezone. Identify the active timezone near the view or in a label where needed.
- Use the standard full date/time format **`yyyy-mm-dd hh:mm:ss`**, with zero-padded fields and a **24-hour clock**: for example, `2026-10-30 07:05:09`. Python's equivalent is `%Y-%m-%d %H:%M:%S`. Date-only values use `yyyy-mm-dd`; time-only values use `hh:mm:ss`. Axis ticks and compact labels may omit context or seconds when appropriate, but never show fractional seconds.
- Apply the rule consistently to tables, details, status timestamps, tooltips, charts and timeline editing views. Localization changes surrounding text, not this numeric format. Convert the instant into local time **before** formatting, and truncate display precision rather than rounding into the next second. Do not display a raw ISO timestamp or use `toISOString().slice(...)` as a local-time formatter.
- Keep persistence and machine-facing timestamp contracts unambiguous: UTC or ISO 8601 with `Z` or an explicit offset where instants are exchanged. The display rule does not change HTTP protocol date headers, database storage, or discard stored subsecond precision. Keep calendar dates as dates rather than converting them into instants.
- Test conversion across midnight and daylight-saving changes, including a browser in a different timezone from the server. Editing local times must reject nonexistent times and disambiguate repeated times, following the timeline contract when that component is selected. Use the approved stdlib modules or browser built-ins; no extra date/time package is required by this standard.

## Trusted HTTP source for security events (only when selected)

When the independently selectable [Security Event Producer]({{ site.baseurl }}{% link pages/component-security-events.md %}) is used in an HTTP application, the **HTTP ingress adapter**, not business logic, identifies the client's verified source address and binds it with the producer's request-scoped `trusted_source(...)` context. Application code then calls only `emit("abuse")`. HTTP itself has no Fail2ban, ZMQ, ban, retry, rate-counter or `bmforge-security-events` dependency when this capability is not selected.

- For direct connections, use the **observed peer address**, not an `X-Forwarded-For` value. Behind a proxy, accept a proxy-provided client address only when the actual immediate peer belongs to an explicitly configured trusted proxy address/network **and** the proxy **overwrites** the selected header using its observed connection (rather than passing arbitrary untrusted values). Reject header spoofing by untrusted peers, and do not trust client-provided request bodies or analytics identities.
- Validate and normalize IPv4/IPv6 numeric addresses with the already-approved stdlib `ipaddress`. Handle direct peers, the exact trusted proxy path, invalid/missing proxy headers, IPv4/IPv6 and deployment listener binding explicitly. A malformed, absent or untrusted address must never be converted to a loggable banning source. Do not silently substitute the proxy address, a loopback address or a made-up client identity.
- Bind and restore the address only for the actual request's lifetime, even when the handler raises. Do not store per-client mutable address state in shared application globals, store flood counters, or forward address parameters through business activities just to emit security events.
- Check the installed reverse proxy and backend listener topology so untrusted direct requests cannot masquerade as proxy requests. These are **source-integrity tests**, not re-tests of the downstream nftables IP-blocking component.

**Acceptance:** exercise an ordinary direct request, a valid trusted-proxy request, a forged forwarded header from an untrusted peer, a trusted-proxy request with a missing/invalid header, both address families, simultaneous requests and restored context after an error. Verify the emitted journal security event has the verified original client address, but do not add a firewall-test gate to the HTTP specification.

## Reference snapshot

- `components/reference/bmgeoip/bmgeoip/server/BMGeoIPServer.py`: listener, CLI binding, integration, lifecycle
- `components/reference/bmgeoip/bmgeoip/server/BMGeoIPHandler.py`: GET/HEAD/POST routing, templates, JSON response, health endpoints
- `components/reference/bmdynip/bmdynip/server/static/index.html`: dark UI structure, semantic controls and status
- `components/reference/bmdynip/bmdynip/server/static/style.css`: reusable palette tokens, action states and responsive rules

The BMGeoIP examples contain GeoIP-specific routes, globals and integration code. **Do not reproduce those behaviours** in unrelated applications. The BMDynIP design snapshots are pinned from [BMDynIP commit 2077300e7ee20de5328164115a277f353ed19579](https://github.com/NadimGhaznavi/bmdynip/tree/2077300e7ee20de5328164115a277f353ed19579); see the [example screenshot](https://github.com/NadimGhaznavi/bmdynip/blob/2077300e7ee20de5328164115a277f353ed19579/pages/images/bmdynip-web-interface.png). They illustrate appearance, not an application to replicate.

## Required contract

- The application supplies the server class/entry point, request handler, routes, and service dependencies.
- Read listener defaults from the application's declared network constants and production overrides; optionally allow explicit CLI overrides. Validate host and port before bind. Publish the listener in `CMDB_NETWORK` and use the Network Configuration process.
- Use a bounded request socket timeout. Bind failure and fatal worker failure must surface as errors; do not claim readiness before successfully binding.
- Implement `GET`, `HEAD`, and only the required mutation methods. A HEAD request sends headers but no body. Unknown routes return 404.
- Return accurate status codes, `Content-Type`, UTF-8 where applicable, `Content-Length`, `Cache-Control: no-store` where appropriate, and `X-Content-Type-Options: nosniff`.
- For JSON writes, validate method, path, Content-Type, request length, schema, and user-supplied fields; reject malformed or oversized requests with 4xx rather than uncontrolled exceptions. Consider origin/access policy for state-changing endpoints; same-origin checks are not authentication.
- Use Jinja2 HTML autoescaping and fail on missing template values; keep templates, static assets and route data application-owned. Never embed secrets in rendered output or public diagnostics.
- Serve `GET /health` on the existing HTTP listener as the application's CMDB-facing check: `200` when its required components are usable, `503` when a known required component is unavailable. Return the small component-status JSON defined by Application Health Checks. A fixed `200` for a running process is insufficient. Do not add a separate `/ready` implementation without a concrete requirement.
- Cleanly close the HTTP listener and any owned background workers during termination, including SIGTERM. No orphaned threads.
- When a human-facing GUI is requested, apply the **GUI design contract** above. An API-only service need not render HTML.
- Apply the **Date and time display** contract to all human-facing timestamps; keep wire/storage timestamps distinct from formatted display text.
- Keep application-specific business logic out of the generic HTTP mechanics. Use typed interfaces or injected collaborators where useful without inventing extra layers.

## Acceptance checks

1. Bind to a test loopback address and ephemeral port; GET known path returns correct body, type and length; HEAD omits body.
2. Unknown route is 404; unsupported mutation and malformed/oversized JSON do not crash the server.
3. HTML user-provided values are escaped; static assets cannot traverse outside allowed paths.
4. `GET /health` returns `200` and component statuses when required components are usable; a simulated ZeroMQ or application DB failure returns `503` with the failed component identified. No direct database probe by CMDB and no new HTTP listener.
5. Address-in-use, invalid port and graceful shutdown are tested; service exits without lingering workers.
6. Confirm the installed application exposes its declared address/port, respects production overrides, and has no runtime import of BMForge/bmgeoip.
7. Verify the HTTP implementation uses the approved runtime modules only; any proposed replacement or addition was approved by the user before implementation.
8. **GUI only:** visually inspect desktop and narrow/mobile pages for a consistent dark, high-contrast, non-pastel palette; legible panels, tables and forms; saturated primary accents; visible keyboard focus; labeled status; and no clipped essential actions. Verify applicable text and control contrast targets. API-only services skip this check.
9. **Timestamp displays:** verify zero-padded local `yyyy-mm-dd hh:mm:ss` output, a 24-hour clock, no fractional seconds and the same display timezone in server/browser rendering. Cover UTC inputs, a different browser timezone, local midnight and daylight-saving boundaries; ensure machine timestamps retain their offset and stored precision.
10. **Security producer only, when selected:** exercise direct and trusted-proxy address extraction, forged/untrusted headers, missing or invalid proxy values, IPv4/IPv6 normalization, request-local context isolation and the installed listener. Business code must only emit a named event, not a source IP or ban request.
