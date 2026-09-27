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
project owner. The project owner is the architect and release manager and
owns all Git operations and releases.

The assistant must never run Git commands or release scripts. This includes
read-only Git commands and invoking release scripts indirectly through tests.
Leave those operations to the project owner. Shell syntax checks that do not
execute the release script are permitted.

## Organize by responsibility

- `index.md` is the sole documentation root.
- `pages/` contains configuration references and project guides.
- `_config.yml` holds Jekyll settings and site-wide layout defaults.
- `scripts/` contains maintenance tooling.
- `VERSION` holds the project version; `0.0.0` is the initial unreleased baseline.
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
