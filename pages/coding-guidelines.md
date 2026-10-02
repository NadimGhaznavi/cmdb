---
title: Coding Guidelines
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

CMDB should be easy to navigate, understand, and maintain. Keep the project
lean and build for the workflows that exist now. Prefer simple Markdown and
the shared theme's existing layouts to custom code or duplicated assets.

## Respect development and release ownership

The AI coding assistant is the lead developer and handles implementation,
checks, and documentation within the architecture and standards set by the
project owner. The project owner is the architect and release manager.
The assistant may perform Git operations and run release scripts as part of
the authorized workflow.

## Organize by responsibility

- `index.md` is the sole documentation root.
- `pages/` contains configuration references and project guides.
- `_config.yml` holds Jekyll settings and site-wide layout defaults.
- `scripts/` contains maintenance tooling.
- `cmdb/` contains Python code grouped into constants, entities, interfaces,
  activities, and server modules. `cmdb/activity/` holds background workflows;
  `cmdb/server/` owns HTTP serving and service lifecycle.
- `cmdb-server.py` is the service entry point; `systemd/` contains its unit template.
- `tests/` verifies HTTP behavior and database contracts.
- `DCMDB.VERSION` in `cmdb/constants/DCMDB.py` holds the project version as a
  literal string.
- `CHANGELOG.md` records user-visible changes and releases.

The shared `NadimGhaznavi/minimal-mistakes` theme owns the site's presentation.
Keep CMDB-specific settings in this repository. Introduce local layout or asset
overrides only when a requirement calls for them.

## Keep documentation focused

Keep `README.md` as a pointer to
[cmdb.osoyalce.com](https://cmdb.osoyalce.com), without duplicating navigation.
Every documentation page must be reachable by following links from `index.md`,
directly or through another reachable page. Update links when adding or moving
content.

Give each page YAML front matter with a lowercase `title` key and one clear
purpose. Use Jekyll's `link` tag for internal page links, prefixed with
`site.baseurl` as on the documentation index. Use fenced blocks for commands
and configuration examples, and tables for structured references.

Document implemented behavior and verified commands. Distinguish examples from
the current network configuration and identify incomplete or outdated records.
Keep credentials, tokens, and other secrets out of this public site.

## Make reviewable changes

Keep database mechanics in `cmdb/interface/DbMgr.py`; domain database interfaces
own application queries. Never share a connection between request threads.
Follow the [model mapping policy]({{ site.baseurl }}{% link pages/project-mission.md %}#model-reference):
map each adopted CWM class directly to a Python entity and database table,
preserving names, attribute casing, inheritance, relationships, and
multiplicities. Implement only the subset the application needs and has data
to store.
Table names must exactly match the singular, capitalized CWM class names,
such as `SoftwareSystem` and `Component`. Do not introduce extra entity or
association tables as substitutes for the adopted model's ownership references.
Do not move inherited attributes onto child classes. Add a parent class and
table only when storage needs its attributes. During initial development,
target fresh schemas and scanner-driven population; do not add migrations for
existing records.
Use bound SQL parameters and explicit transactions for related writes. Validate
external configuration at the boundary and let internal programming errors
surface. Keep presentation separate from database access and application logic.

Run the Python checks in [CMDB server]({{ site.baseurl }}{% link pages/server.md %})
when modifying the backend. This server environment is separate from the
GitHub Pages build.

Keep each change coherent. When moving a page, update incoming links and check
its generated URL. Preserve existing behavior unless the task calls for a change.
GitHub Pages builds the site. Do not add a Gemfile or require local Jekyll
builds. Keep generated site output out of source control.

Follow the checks in [Site development]({{ site.baseurl }}{% link pages/development.md %}).
Verify page titles, navigation, rendered tables, code blocks, and theme assets
when changing presentation. Report checks that could not be run.

## Update the changelog

Record meaningful changes under `## [Unreleased]` in `CHANGELOG.md`. For changes
with many details, add a `### Summary` explaining the problem and solution in
one or two sentences. The release script assigns the version and timestamp.
