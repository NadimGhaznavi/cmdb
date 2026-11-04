---
name: bmforge-visualization
description: Implement application-owned browser charts with Plotly.js, geographic maps with Leaflet, or topology/relationship graphs with Cytoscape.js at BMForge-approved versions. Use when an HTTP UI needs visualization.
---

# Display visualizations

Read `references/specification.md` and `references/engineering-contract.md`. Choose only the capability required by this application's UI:

- **Charts:** Plotly.js **4.1.1**, following pinned MyCount examples in `references/source/mycount/`. This is browser-side JavaScript, **not** Python's `plotly` package.
- **Maps:** Leaflet JS and CSS **1.9.4**, following pinned MyCount visitor map examples. Respect map tiles' service terms/attribution.
- **Topology graphs:** Cytoscape.js **3.34.3**, following pinned CMDB templates and JavaScript. The exact approved local vendor file and licence are at `references/source/cmdb/cmdb/server/static/vendor/`; copy them into the app only if a graph requires them.

Build visualization inside the existing HTTP UI. Backend data comes from application activities and interfaces, not browser-rendering libraries. Pass structured data safely, keep user-facing HTML labels escaped, and do not invent an additional frontend framework or plotting backend.

The selected browser libraries do not change the HTTP server's Python module inventory. No implicit upgrade, substitution or cross-app runtime import. Verify browser rendering against the user-selected chart/map/graph use case.
