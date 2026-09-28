---
title: Changelog
permalink: /CHANGELOG/
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## [Unreleased]

### Added

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
