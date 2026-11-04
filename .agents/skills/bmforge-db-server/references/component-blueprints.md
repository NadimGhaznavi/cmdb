---
title: Component Blueprints
lang: en
locale: en-US
language_name: English
translation_key: bmforge-component-blueprints
---

All implementations follow [Activity / Interface / Entity classification]({{ site.baseurl }}{% link pages/classification.md %}) and the [engineering contract]({{ site.baseurl }}{% link pages/engineering-contract.md %}) and, for running applications, [application health checks]({{ site.baseurl }}{% link pages/health-checks.md %}). For stable IDs, version tags, and specification changes see [traceability]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

BMForge is a **standalone specification and reference-code repository**, not a shared runtime library, package registry, or framework dependency. A new application owns its generated/copied code. Do not import BMForge or another project's Python modules in production. Cross-project integration is permitted only via the other project's explicitly documented public API.

Every new application uses the pinned [constants]({{ site.baseurl }}{% link pages/component-constants.md %}), [application localization]({{ site.baseurl }}{% link pages/component-localization.md %}), and [installation lifecycle]({{ site.baseurl }}{% link pages/component-installation.md %}) **standards** from the beginning. Constants define stable program identifiers; locale catalogues define the user-visible text. Neither adds a server or selects an unrequested technology.

Display-visualization libraries are selected by requested **capability** (chart, geographic map or relationship graph) under the [visualization component]({{ site.baseurl }}{% link pages/component-visualization.md %}); they do not become dependencies of every HTTP server. **Module lists are mandatory, not suggestions.** The **Approved runtime modules** section of each selected component is the complete technology inventory for that component's reusable infrastructure. Codex may supply local names, constants and bindings, but must pause for user approval if a requirement cannot be met with those modules. No ad hoc replacement with a new server, driver, ORM, broker, or UI library. Application-specific activities and separately approved components have their own dependencies.

## Project-local Codex skills

Use the [Codex bootstrap]({{ site.baseurl }}{% link pages/codex-skills.md %}) to install selected skills under the consuming application's `.agents/skills/`. Each skill packages the relevant, immutable local reference snapshot and the authoritative contract as it was at installation. Pinned skills remain unchanged until the user approves an update; the installed manager only **checks and notifies**.

Installing the Codex skills does not install an application. After requirements are known, the **installation** skill requires Codex to complete and test all three lifecycle operations before the first release, with a versioned `/opt/prod` footprint even for a custom library or client-only program. Use DevLog's frozen role-aware example only when a genuine split client/server topology is required.

The optional [Timeline Editing component]({{ site.baseurl }}{% link pages/component-timeline.md %}) requires HTTP. Select both skills explicitly, or add timeline to a project with HTTP already pinned; the manager checks the prerequisite before writing files.

## Codex workflow

For a producer-only application, select [Security Events]({{ site.baseurl }}{% link pages/component-security-events.md %}) **alone**. Business code emits a semantic event; the trusted ingress adapter supplies the verified address and the systemd journal carries the log. No HTTP, ZMQ, Fail2ban or nftables skill dependency is implied. For a blocking/consumer project, select [Fail2ban]({{ site.baseurl }}{% link pages/component-fail2ban.md %}) for native **journald** detection and its thin ban action, [ZMQ]({{ site.baseurl }}{% link pages/component-zmq.md %}) for communication, and [nftables]({{ site.baseurl }}{% link pages/component-nftables.md %}) for timed bans. Fail2ban still requires ZMQ in that project. All detection windows/counts belong to native Fail2ban, never to the producer. No new file log or ban-state machinery is selected.

1. Select only the components requested by the application's requirements. Read each specification in full.
2. For HTTP and ZeroMQ, inspect the pinned examples under `components/reference/bmgeoip/` as **local reference snapshots**, then adapt the relevant mechanics into the application. For MariaDB, copy `components/templates/db-server/interface/DbMgr.py` **unchanged** into the application and build only the required domain `*Db` interfaces above it. Use the Git component's own standalone template for Git. Never fetch moving upstream source.
3. Replace BMGeoIP-specific names, routes, configuration, schema, message methods, resource paths and lifecycle hooks in adapted HTTP/ZeroMQ code. Never copy GeoIP business functionality into an unrelated application. For the DB Server, supply the application's resolved configuration **without editing the canonical manager**. Keep business SQL only in new domain `*Db` interfaces.
4. Classify application classes as `activity/`, `interface/`, or `entity/` by responsibility before implementing them, following the [classification contract]({{ site.baseurl }}{% link pages/classification.md %}). Use composition, not an invented class hierarchy. Follow BMForge's existing runtime/network configuration, installation, and CMDB processes. The project owns its configuration, service units, tests, database schema, and deployment.
5. Implement the acceptance checks in each chosen specification. Test failure handling, startup/shutdown, and real boundaries. Report checks run and any deviations.
6. Match the selected specification's approved modules exactly for the component infrastructure. Do not add a third-party dependency, replace an approved library, or create a different implementation to satisfy an unstated preference. If the prescribed modules are insufficient, stop and ask the user to amend or add a component first.
7. Avoid speculative infrastructure, layers, dependencies, and features. Ask before broadening scope.
8. Implement the selected components' on-demand health checks via the application's existing interfaces. CMDB must ask the application rather than the database directly.
9. Place the chosen component's literal `BMFORGE_COMPONENT` marker in its owning implementation module, using the ID and version shown by the component specification. This is provenance, not a runtime dependency or a compliance certificate.

Animated GIF exports are separately covered by [GIF Animation]({{ site.baseurl }}{% link pages/component-gif-animation.md %}). This backend Pillow encoder does not replace Plotly.js or imply that every browser dashboard needs GIF generation.

## Blueprints

- [Project GitHub Pages: shared theme, required logo and site scaffold]({{ site.baseurl }}{% link pages/jekyll-setup.md %})
- [HTTP Display Server]({{ site.baseurl }}{% link pages/component-http.md %})
- [Timeline Editing: vis-timeline, requires HTTP]({{ site.baseurl }}{% link pages/component-timeline.md %})
- [ZeroMQ Request/Reply Server]({{ site.baseurl }}{% link pages/component-zmq.md %})
- [Timed Host IP Bans: nftables]({{ site.baseurl }}{% link pages/component-nftables.md %})
- [Security Event Producer: fire-and-forget journald, no prerequisites]({{ site.baseurl }}{% link pages/component-security-events.md %})
- [Security Journal Detection: Fail2ban, requires ZMQ only in blocking project]({{ site.baseurl }}{% link pages/component-fail2ban.md %})
- [DB Server]({{ site.baseurl }}{% link pages/component-db-server.md %})
- [Display Visualizations: charts, maps and graphs]({{ site.baseurl }}{% link pages/component-visualization.md %})
- [GIF Animation: rendered frames to animated GIF]({{ site.baseurl }}{% link pages/component-gif-animation.md %})
- [Constants]({{ site.baseurl }}{% link pages/component-constants.md %})
- [Application Localization]({{ site.baseurl }}{% link pages/component-localization.md %})
- [Installation Lifecycle]({{ site.baseurl }}{% link pages/component-installation.md %})

## Reference provenance

The vendored example files in `components/reference/bmgeoip/` are copied from `NadimGhaznavi/bmgeoip` at commit `35c8745c7003a124dce5b5799b08b2d7c851fbfc` (24 October 2026). They are immutable examples from that revision, not live links, and must not be periodically synchronised without review. The source file layout is retained to show component boundaries and imports. Some examples depend on BMGeoIP-only modules intentionally not part of the component catalogue; implementation agents must replace those integrations, not attempt to run the snapshot as a standalone application. Each component contract names exactly which Python import modules are approved. Third-party package versions are installed and tracked in the **generated application's** dependency files, with deliberate upgrades.

The HTTP component additionally provides BMDynIP's **frozen HTML/CSS visual references** under `components/reference/bmdynip/bmdynip/server/static/`, pinned to commit `2077300e7ee20de5328164115a277f353ed19579`. New human-facing pages use them as design inspiration for dark, saturated, high-contrast interfaces without fixed hex colors, copied DNS functionality or a BMDynIP runtime dependency. API-only services do not acquire a GUI.

The visualization component has frozen local MyCount Plotly/Leaflet and CMDB Cytoscape source examples under `components/reference/`. Its approved JavaScript libraries are independent of the Python HTTP transport's module list and require explicit selection by application need.

## Component boundaries

The HTTP server owns request/response mechanics; application handlers own routes, HTML, API behaviour and policy. The ZMQ transport owns socket/message lifecycle; application handlers own command semantics. The canonical database manager owns connection/transaction mechanics; one or more application-specific `interface/*Db.py` classes own SQL, schema and record mapping. `activity/` coordinates named operations and `entity/` holds data. Do not make components depend on one another unless an explicit application data flow requires it.

**Completion rule:** a component is delivered only after it runs and passes its specified acceptance checks in the consuming project. Documentation or copied files alone do not qualify.
