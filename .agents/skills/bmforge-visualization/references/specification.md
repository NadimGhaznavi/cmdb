---
title: Display Visualizations Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.visualization"
spec_version: "0.1.0"
spec_status: "draft"
translation_key: bmforge-component-visualization
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

This component fixes the **approved browser visualization libraries** for application dashboards. It is not another HTTP server, plotting service, Python package, JavaScript framework, or reusable data-access abstraction. Select only the visualization capability the application's requirements actually need. Backend HTTP, Jinja2 template rendering and MariaDB access remain governed by their own BMForge contracts.

## Approved runtime modules

| Requested capability | Approved browser library | Current approved version | Reference implementation |
| --- | --- | --- | --- |
| Charts: line, bar, histogram, pie, timelines and interactive data plots | **Plotly.js** | **4.1.1** | MyCount `Plotly.newPlot(...)` |
| Geographic map: pan, zoom, tiles, position markers and popups | **Leaflet** (JavaScript **and CSS**) | **1.9.4** | MyCount `L.map(...)`, `L.tileLayer(...)`, `L.circleMarker(...)` |
| Relationship, network or topology graph: nodes, edges, layout and selection | **Cytoscape.js** | **3.34.3** | CMDB `cytoscape({ ... })` machine/deployment graphs |

**This is an allowlist, not a requirement to load all three.** If a page needs only a chart, load Plotly.js and ordinary browser JavaScript/CSS, not Leaflet and Cytoscape. If it needs both a chart and a map, select both explicitly. The relevant library is the sole approved third-party browser visualization dependency for that capability; the browser's built-in DOM, Fetch, JSON and CSS APIs need no other library.

**No silent substitution or upgrade:** Do not swap Plotly.js for Chart.js, D3, ECharts, Bokeh or Matplotlib; Leaflet for another mapping package; or Cytoscape.js for another graph toolkit. Do not introduce React, Vue, a frontend build tool, a chart wrapper, a CDN `latest` URL, or a new plotting backend merely because Codex prefers it. If the chosen library cannot satisfy a real requirement, **stop and ask the user** to approve an alternative or a new version, then revise this BMForge specification before implementing it.

The **Python `plotly` package is not required** by this component: MyCount draws charts with browser-side Plotly.js, which is absent from its Python `requirements.txt`. Jinja2 (`jinja2`, MyCount currently `>=3.1,<4`) is an existing *server-side HTML templating* choice already approved by [HTTP Display Server]({{ site.baseurl }}{% link pages/component-http.md %}); it is not a plotting library and is not a required dependency of this component. CMDB's current display template is rendered by simple placeholder replacement, **not** Jinja2.

## Approved asset delivery

The pinned reference deployments establish these exact ways to load the libraries:

- **Plotly.js 4.1.1:** MyCount loads `https://cdn.plot.ly/plotly-4.1.1.min.js` from a versioned URL.
- **Leaflet 1.9.4:** MyCount loads the matching JavaScript and CSS from `https://unpkg.com/leaflet@1.9.4/dist/`, with fixed integrity values in the pinned source.
- **Cytoscape.js 3.34.3:** CMDB serves `/static/vendor/cytoscape-3.34.3.min.js` locally. BMForge includes the **byte-for-byte local vendor file and its license** under `components/reference/cmdb/cmdb/server/static/vendor/` so a new project can copy the approved version without fetching from CMDB.

A consuming application owns its assets, URLs and dependency declarations. Use the documented reference delivery method for the selected capability unless the user approves a different distribution or versioning approach (for example, packaging Plotly locally for offline access). **Do not import code or assets at runtime from another application.** Installing an approved browser dependency does not change the Python module inventory of the HTTP server.

Leaflet map **tile services** are an external data/service dependency, not a substitute mapping library. MyCount currently uses OpenStreetMap tiles with attribution. If a new project requires a different tile provider or offline maps, decide its service/usage contract explicitly rather than hiding it in the Leaflet component.

## Presentation boundary

The application computes and retrieves data using its normal activities and interfaces; the display layer only turns supplied values into visual elements. For server-rendered pages using Jinja2, enable HTML autoescaping and pass data to JavaScript through its `tojson` filter. For JSON endpoints, provide structured JSON and treat fields as data. Use `textContent` or equivalent DOM-safe APIs for untrusted labels and map popup content, rather than interpreting text as HTML.

Render into a defined DOM container with the selected library's documented API. Keep the chart type, axes, colour choices, layout, interactive selections and refresh rules in the owning application. This component does **not** prescribe or generate a generic chart registry, data model, API server, background polling job, or application-specific graphics. Do not change an existing visualization library when maintaining another feature.

The visualization lives inside the application's **existing** display server and has **no independent listener, database access or `/health` endpoint**. The application's existing health contract remains unchanged.

## Frozen, local reference code

The following original files are copied into BMForge, retaining their upstream paths. They are **reference snapshots, not complete runnable standalone applications**.

**MyCount** source commit `90574cd838ba43499a825c6a193b43cbc485c91c`:

- `components/reference/mycount/mycount/server/ControlPages.py` and `.../templates/base.html`: Python Jinja2 page renderer and layout
- `.../templates/chart_theme.html`: pinned Plotly.js script and shared chart style
- `.../templates/all_traffic.html`, `.../templates/pie_charts.html`, `.../templates/marketing_chart.html`: Plotly data rendering examples
- `.../templates/visitor_map.html`: pinned Leaflet JavaScript/CSS, OpenStreetMap tiles and safe popup construction

**CMDB** source commit `43438d9c41949ef70a635884a9bd6885d5c5f22c`:

- `components/reference/cmdb/cmdb/server/templates/home.html`: local Cytoscape script inclusion and graph container
- `components/reference/cmdb/cmdb/server/static/machines.js`: Cytoscape nodes, layout, styling and event handling (also contains unrelated CMDB application code)
- `components/reference/cmdb/cmdb/server/static/vendor/cytoscape-3.34.3.min.js` and `.../cytoscape-LICENSE`: the exact locally bundled dependency and licence

Read the relevant reference files only; **do not copy application-specific routes, reports, machine operations, scheduling or persistence code**. The approved choices and versions above are the BMForge contract. The source snapshots preserve their provenance without runtime coupling.

## Traceability and version maintenance

Record the selected visualization capabilities and library versions in the consuming application's source/dependency documentation. If a Python page-rendering module clearly owns this component, it may use the standard literal `BMFORGE_COMPONENT` marker for `bmforge.visualization` at `0.1.0`. Do **not** add a synthetic Python service just to hold a marker. Automated JavaScript asset scanning by CMDB is not implemented.

A future library upgrade is an explicit user-approved revision to this specification, not a silent dependency update or replacement during another task. Validate rendering and interactions in the consuming application after any approved change.

## Acceptance checks

1. New chart, geographic map and topology graph requests select Plotly.js, Leaflet and Cytoscape.js respectively; unrelated libraries are not loaded.
2. Pin exact approved library versions and appropriate JavaScript/CSS assets; do not use moving `latest` references.
3. Confirm charts, maps and graphs render the application's supplied data with required interactivity, labels and error states; do not assume an unchanged HTTP health response proves correct browser rendering.
4. Escape or safely serialize untrusted values and preserve required map attribution.
5. Confirm the visualization uses no unapproved plotting package or frontend framework, and application logic remains outside frozen reference infrastructure.
6. Verify any change to a visualization technology or approved version was agreed with the user and documented in a new BMForge specification revision.

---

[Component Blueprints]({{ site.baseurl }}{% link pages/component-blueprints.md %}) · [Back to BMForge]({{ site.baseurl }}{% link index.md %})
