---
title: Changelog
permalink: /CHANGELOG/
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## [Unreleased]

## [0.3.4] - 2026-09-27 @ 20:57

### Changed

- Styled machine nodes dark green with bold white 24px labels.

## [0.3.3] - 2026-09-27 @ 20:54

### Changed

- Changed the machine graph to a circle layout, including when the panel resizes.

- Resolve missing scan hostnames through reverse DNS, retaining records when lookup fails.
- Place hostname and IP labels inside larger machine bubbles.

## [0.3.2] - 2026-09-27 @ 20:48

### Fixed

- Limited the generated-site vendor ignore rule to the repository root so the
  bundled Cytoscape.js library and license can be included in deployments.

## [0.3.1] - 2026-09-27 @ 20:39

### Changed

- Moved Last refresh to the bottom-right corner, opposite the Refresh button.

### Added

- Bottom-left Refresh button to reload the machine graph and page timestamp.

## [0.3.0] - 2026-09-27 @ 20:34

### Changed

- Removed the database readiness and documentation links from the landing page.
- Boxed the landing-page title and horizontal rule, and replaced the running
  message with the page refresh time in `MMM DD - HH:MM:SS` format (server local time).

### Added

- Full-height machine panel using locally bundled Cytoscape.js, a database-backed
  machine endpoint, and clickable nodes showing stored machine details.
- Periodic machine discovery with a configurable scan interval, database upserts,
  and `createdOn` / `updatedOn` timestamps, including existing-table upgrades.
- External `schema/cmdb-schema-v1.sql` applied during installation and upgrades to
  create the `machines` table with the Machine entity's attributes.
- Machine entity with `ipAddress`, `hostName`, `site`, and `deployedComponent` attributes.
- Nmap interface using python-nmap for network scans, with configurable targets,
  ports, scan arguments, and timeout.

## [0.2.0] - 2026-09-27 @ 19:20

## [0.1.0] - 2026-09-27 @ 19:11

### Summary

Establish CMDB's documentation and release foundation using the MyCount project
conventions and shared Minimal Mistakes theme.

### Added

- CMDB server on port 14444 with a landing page, health and MariaDB readiness endpoints.
- MyCount-style account and database provisioning, private credentials, virtual environment, systemd service, and repeatable upgrade scripts.
- Server installation documentation and HTTP/database contract tests.
- Project mission, development guidance, contributor instructions, and release documentation.
- A maintainer-run feature → dev → main release script, version file, and changelog.
- Ignore rules for generated site files.

### Changed

- Build and publish through GitHub Pages, with source checks before release.
- Use the dark Minimal Mistakes theme with an author sidebar and shared page defaults.
- Correct homepage links for the references moved into `pages/`.
- Add AutoFS front matter and correct the Port Numbers title key.
