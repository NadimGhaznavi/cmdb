---
title: Changelog
permalink: /CHANGELOG/
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## [Unreleased]

### Added

- Store Linux release ID and full Debian version on SoftwareSystem, with the
  release codename in CWM TaggedValue attached through ModelElement.

- Collect OS release information alongside hostnames and MAC addresses through
  the shared local/SSH path, updating the existing OS deployment at `/`.

### Fixed

- Execute SSH-interface commands directly for local targets and skip local SSH
  provisioning. Share hostname and interface MAC collection across local and
  remote machines, populating the CMDB host's MAC when Nmap omits it.

## [0.5.3] - 2026-09-28 @ 09:03

### Changed

- Move MachineScanner to `cmdb/activity`, keeping its lifecycle managed by the server.

### Added

- SSH follow-up after scanning: test port 22 and `cmdb` login, provision the remote
  account and public key through root when needed, retest, and store its hostname.
  New host keys are recorded in the persistent local known-hosts file.
- Optional remote `user` for SSH commands, including direct root login using the
  existing local `cmdb` key without local sudo.
- SSH interface for remote commands as `cmdb`, with a persistent local Ed25519
  key generated during installation and retained across uninstall/install.
- `DLabel.py` maps model attribute names to readable GUI labels in machine details.

### Fixed

- Enforce agreement between `DeployedComponent.machine` and inherited
  `ModelElement.namespace` with a composite foreign key; document the invariant
  in Schema Notes.

## [0.5.2] - 2026-09-28 @ 08:12

### Fixed

- Match table names to CWM class names exactly and replace the extra deployed
  software system layer with SoftwareSystem ownership of Component.
- Store ownership on ModelElement and Namespace, with shared parent/child IDs,
  rather than copying inherited fields onto software deployment classes.
- Update backend queries and fresh-schema tests for the corrected model.

## [0.5.0] - 2026-09-28 @ 07:33

### Added

- OS scanning with SoftwareSystem, Component, and DeployedSoftwareSystem entities
  and tables, linked to each machine through its root DeployedComponent.
- Separate OS scan timeout and reporting documentation. Inconclusive OS results
  preserve stored classifications; failed OS scans retain machine discovery.

### Changed

- Use fresh-install schemas without record migrations during initial development.
- Represent `Machine.deployedComponent` as a collection of deployment IDs.
- Clarify that storage needs determine the CWM subset and that inherited
  attributes stay on their owning parent classes.
- Document CWM 1.1 SoftwareDeployment as the core model reference, with scope
  limited to the classes, attributes, and relationships the application needs,
  and require one-to-one mapping to Python entities and the database schema.
- Installer completion message now reports `CMDB server listening on port: 14444`.

## [0.4.2] - 2026-09-28 @ 07:07

### Changed

- Install a passwordless sudoers rule granting `cmdb` unrestricted arguments to
  root Nmap scans; the interface now uses sudo and the service permits privilege
  elevation. Uninstall removes the rule while retaining credentials and accounts.

## [0.4.0] - 2026-09-28 @ 07:00

### Added

- `scripts/uninstall.sh` removes the installed service, application, and database,
  retaining credentials and accounts for reinstallation.

## [0.3.14] - 2026-09-28 @ 06:49

### Added

- Optional Machine `macAddress`, populated from Nmap when available, persisted
  across scans, and displayed in machine details; includes existing-table migration.
- Standalone ProviderConnection entity with a required `dataProvider` owner reference.
- DataProvider entity inheriting from DataManager, with a `resourceConnection`
  list supporting zero or more ProviderConnection objects.
- DataManager entity inheriting `pathname` and `machine` from DeployedComponent.

- DeployedComponent entity with required `pathname` and `machine` attributes,
  and a `deployedComponents` table linking multiple components to stable `machines.id` values.
- Auto-increment machine IDs, including migration of existing machine records.

## [0.3.13] - 2026-09-27 @ 21:52

### Changed

- Display named machines as uniform 160 × 80 rounded rectangles; unnamed machines remain circles.

## [0.3.11] - 2026-09-27 @ 21:40

### Changed

- Sort the machine dropdown by unqualified hostname, followed by unnamed machines
  in numeric IP order; re-sort after hostname edits.

## [0.3.10] - 2026-09-27 @ 21:38

### Changed

- Replaced the machine count and selection hint with the left-aligned machine dropdown.

- Moved Edit, Save, and Cancel into the details panel, left-aligned below the table.

## [0.3.9] - 2026-09-27 @ 21:34

### Changed

- Display machine timestamps and Last refresh in browser-local time using
  `YYYY-MM-DD HH:MM:SS`, preserving stored precision.
- Moved selected-machine details to a key/value table left of the graph, stacking
  above the graph on narrow screens.

## [0.3.8] - 2026-09-27 @ 21:27

### Changed

- Show machines without hostnames as grey nodes, including a lighter grey when selected.

### Removed

- Automatic hostname discovery: disabled Nmap DNS resolution and removed reverse
  lookups. Scans preserve hostnames, which are maintained through manual editing.

## [0.3.7] - 2026-09-27 @ 21:22

### Changed

- Refresh now signals the scanner worker, waits for scan completion, and reloads
  the inventory. Concurrent refreshes share the active scan; failures are shown in the UI.

## [0.3.6] - 2026-09-27 @ 21:12

### Added

- Edit, Save, and Cancel controls for the selected machine's hostname, with
  database persistence and immediate graph/detail updates. Scans retain existing hostnames.

### Changed

- Reduced machine labels to 16px and darkened unselected nodes, using the previous
  green for selected nodes.

## [0.3.5] - 2026-09-27 @ 20:59

### Changed

- Use 18px machine labels showing the capitalized, unqualified hostname when
  available, otherwise the IP address.

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
