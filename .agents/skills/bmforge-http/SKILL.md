---
name: bmforge-http
description: Implement a standard-library Python HTTP UI/API with the BMForge transport contract; human-facing HTML uses BMDynIP-inspired dark, high-contrast styling with AI-selected saturated accents.
---

# HTTP Display Server

Read `references/specification.md`, `references/engineering-contract.md` and `references/health-checks.md` before implementation. The fixed Python module inventory appears in `references/specification.md`.

- Inspect the **frozen** BMGeoIP HTTP examples under `references/source/bmgeoip/bmgeoip/server/`. These illustrate transport only, not an application to copy wholesale.
- **For human-facing HTML**, inspect the frozen BMDynIP `references/source/bmdynip/bmdynip/server/static/index.html` and `style.css`. Follow the dark, organized panel/table design, **not** BMDynIP's DNS logic, branding or exact colors. **Let the AI choose an application-specific dark palette with saturated primary accents and high contrast; no pastels.** Use CSS tokens, readable forms and statuses, visible focus and mobile-friendly layouts. The GUI acceptance contract is in `references/specification.md`. API-only services need no GUI.
- Build an **application-owned** `http.server.ThreadingHTTPServer` and request handler; choose actual routes, bind port/interface, templates, and configuration from this application's requirements. Use Jinja2 only when rendering HTML. No Flask, FastAPI, Django or replacement framework without approval.
- Supply an on-demand `GET /health` through this HTTP application, including relevant internal checks on existing component interfaces. No new monitoring daemon.
- When providing a user-facing UI, apply the already-installed `bmforge-localization` skill for translated text, request-local language selection and HTML `lang`, without changing the HTTP transport's approved Python module list.
- Display timestamps in the application's local timezone (default: server local time), consistently in server and browser views. Use `yyyy-mm-dd hh:mm:ss`, zero padding and a 24-hour clock; never display fractional seconds. Apply this to tooltips and selected visualization/timeline views too. Keep UTC/offset-bearing machine timestamps and persistence separate from display strings; follow the specification's timezone and daylight-saving checks.
- **Only when a security-event producer is selected:** resolve the real client source at the HTTP ingress boundary. Behind a proxy, trust the forwarded address only from an explicitly trusted immediate peer and an overwriting proxy header. Reject forged/missing/invalid values, normalize numeric IPv4/IPv6, bind per-request context for `bmforge-security-events` and restore it reliably. Business logic emits an event name only; HTTP does not import Fail2ban/ZMQ, count attempts or request bans. Test both direct and proxied paths and installed listener exposure.
- Keep workflow logic in `activity/`, external and domain bridges in `interface/`, and data values in `entity/`. Request handlers must not issue SQL directly.
- Place the literal `BMFORGE_COMPONENT` marker with ID `bmforge.http-server` and spec version `0.5.1` in the owning implementation module.
- Run the contract's acceptance tests in the consumer. Do not treat copying the example as completion.
