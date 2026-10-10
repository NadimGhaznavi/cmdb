---
title: Changelog
permalink: /CHANGELOG/
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## [Unreleased]

The **Karen** is dedicated to [Karen Uhlenbeck](https://en.wikipedia.org/wiki/Karen_Uhlenbeck).

- Keep MariaDB client providers out of the Inventory Component table while
  showing the application's database names above it.

## [1.3.0] - 2026-10-10 @ 08:15

The **Julia** release is dedicated to [Julia Robinson](https://en.wikipedia.org/wiki/Julia_Robinson).

- Show an application's discovered database names above its Component table in
  the Inventory detail sidebar, comma-separated when more than one is present.

- Discover literal `CMDB_DATABASES` declarations, refresh same-machine MariaDB
  inventory, and connect matching catalogs through a MariaDB Client DataProvider
  and ProviderConnection. Reuse client identities across scans and upgrades;
  application deletion preserves the server and backup history.
- Store MariaDB database inventory as relational Catalogs in the fresh schema.

## [1.2.0] - 2026-10-10 @ 07:41

The **Hilda** release is dedicated to [Hilda Geiringer](https://en.wikipedia.org/wiki/Hilda_Geiringer).

- Show named deployed components in application details with a Component / Path
  table, linked directory names, and full paths on hover. Group components under
  their app instead of displaying duplicate applications in Inventory.

- Select Inventory applications independently, highlight the selected software,
  and show only its details. Deselecting closes the sidebar.

- Hide the Inventory details sidebar when the selected machine is deselected.

- Add Discovery to the right of Backups with an enabled flag, cron schedule,
  Update, and Scan Now. Periodic discovery runs independently through cron;
  the web worker scans only on explicit requests, with no startup or interval scan.

- Discover optional literal `CMDB_COMPONENTS` declarations in application constants
  and store named Components with per-machine DeployedComponents for persistent
  filesystem data. Resolve relative paths from the app installation, reuse
  records across scans, and preserve deployment IDs across release changes.

## [1.1.2] - 2026-10-07 @ 06:16

- Keep inventory machine and software selection available while a scan runs,
  so stored details can be inspected without waiting for scan completion.

## [1.1.1] - 2026-10-05 @ 17:30

- Standardize the release script with reusable project settings, an interactive
  release confirmation, and colorized `[ PASSED ]`, `[ FAIL ]`, and `[ WARNING ]`
  progress messages. Set `CMDB_CODENAME` from the supplied release message.

- Sort Inventory applications alphabetically, keeping the OS first and MariaDB
  second when present.

- Display the Software System type `application` as `Application` in registered
  applications and Inventory details.

## [1.1.0] - 2026-10-05 @ 03:34

- Read optional `CMDB_TYPE`, `CMDB_SUBTYPE`, `CMDB_SUPPLIER`, and `CMDB_CODENAME`
  literal strings alongside application `VERSION` during discovery. Store them
  through CWM SoftwareSystem and TaggedValue, preserve omitted metadata, and
  keep classified applications discoverable on later scans.
- Replace the combined scanner activities with InventoryCoordinator and five
  observation sources under `cmdb/activity/sources/`. Workloads run sequentially
  through a FIFO queue, with persistence owned by the coordinator.
- Queue application discovery when an application is added, protecting the new
  definition until its discovery attempt completes.
- Automatically prune SoftwareSystems without deployed components and their
  unused Components after every workload; report each removal in Status Messages.
- Wait for Add Application discovery and pruning before refreshing both application tables,
  and report the outcome of the requested scan when later requests are running.

## [1.0.9] - 2026-10-04 @ 05:47

## [1.0.7] - 2026-10-03 @ 17:43

- Use regular font weight for application labels inside Inventory machine boxes.

## [1.0.5] - 2026-10-03 @ 13:10

- Rename the Inventory Refresh button to Re-Scan Network.

## [1.0.4] - 2026-10-03 @ 13:06

- Keep Inventory Refresh working when an application is deleted during discovery:
  skip the removed definition instead of crashing the scanner, and lock existing
  definitions while recording their deployments.

## [1.0.3] - 2026-10-03 @ 07:20

- Compact Inventory machine and application nodes using a shared size based on
  the widest displayed label plus padding; reduce spacing inside machine groups.

## [1.0.2] - 2026-10-03 @ 07:06

- Reduce Inventory application label font size to 16px to match machine labels.

## [1.0.1] - 2026-10-03 @ 07:04

- Reduce Inventory machine label font size from 24px to 16px.

## [1.0.0] - 2026-10-03 @ 06:57

- Group Inventory machines into stacked, collapsible Production, Quality Assurance,
  Development, and Unclassified boxes with machine counts and responsive grids.
  Saving a machine environment moves it into its new group immediately.

## [0.15.14] - 2026-10-02 @ 18:35

- Make Deployed Applications and Registered Applications collapsible, initially
  showing only their heading titles. Expand a heading to access its table and controls.

## [0.15.13] - 2026-10-02 @ 18:19

- Rename the constants module and class to `DCMDB`, and move the project version
  into its literal `VERSION` constant so CMDB can discover its own installation.
  Update imports, installation tooling, and releases to use the new version source.

## [0.15.12] - 2026-10-02 @ 18:07

- Add a confirmed Delete action to each Registered Applications row. Remove the
  selected definition and its application deployments from CMDB, then refresh
  both tables. Preserve MariaDB backup history and files, disable its backup
  schedules, and reuse retained database inventory when rediscovered.

## [0.15.11] - 2026-10-02 @ 17:41

- Rename the Add Application panel to Registered Applications and list every
  stored SoftwareSystem above an inline Application Name field and Add Application
  button. Refresh the registered table after adding an application.

## [0.15.10] - 2026-10-02 @ 05:58

- Split Backup Vault's backup timestamp into Date and Time columns, and add
  per-column text filters below the headings with a Clear filters button.

- Make the entire Backup Vault collapsible, initially showing only its title row
  with the most recent successful backup time right aligned in `YYYY-MM-DD HH:MM` format.

- Hide Backup Vault's Status column until Scan Filesystem is clicked, and hide
  it again when the table refreshes.

- Leave missing values and unchecked filesystem statuses blank in Backup Vault.

- Add Size after Filename in Backup Vault, displaying recorded backup sizes
  in human-readable units such as KB and MB.

- Add a machine environment dropdown (Unclassified, Prod, QA, DEV) and an
  Update button beside Re-Scan in selected inventory machine details. Save
  `DeploymentEnvironment` as a TaggedValue on the machine's ModelElement,
  updating or creating it for dev, qa, and prod, and deleting it for Unclassified.
  Load saved classifications when selecting machines and show save results.

- Report `Scan complete` when scanning finishes, keeping individual application
  read failures in status history without failing the overall scan.

## [0.15.8] - 2026-10-01 @ 05:19

- Detect installed applications using only their `D`-prefixed constants files
  (such as `DMyCount.py`).

- Report `Inventory scan complete` when an inventory scan finishes successfully.

## [0.15.7] - 2026-10-01 @ 05:07

- Use unqualified, lowercase hostnames in application scan status messages when
  available, falling back to the IP address for unnamed hosts.

- Display Status Messages in a table with Timestamp, Source, and Message columns,
  recording each entry's time and showing it as `YYYY-MM-DD HH:MM:SS` in local time.

## [0.15.6] - 2026-10-01 @ 04:52

- Increase inventory graph labels to 24px bold, use blue for machine selection,
  and give application boxes a lighter shade of their machine's background.

## [0.15.5] - 2026-10-01 @ 04:44

- Give the inventory graph its own box and show selected machine details in a
  separate box on the left, stacked above the graph on narrow screens.

- Apply MyCount’s warm dark application theme to CMDB panels, tables, controls,
  navigation, status messages, and inventory graph states.

## [0.15.3] - 2026-10-01 @ 04:35

- Changed the app's default background color to black.
- Applied a Mondrian color theme with red, yellow, blue, and warm white accents
  across navigation, controls, panels, and inventory graph states.

## [0.15.1] - 2026-10-01 @ 04:28

- Log application scan results as one-line status messages with host, application,
  and detected version, or a brief missing/read-failure outcome.
- Include the calling module's name in each status message's `source` field
  and display it before the message in the Status Messages box.
- Add a shared Status Messages box to all CMDB screens with five visible lines,
  scrollable history, and live scan updates. Keep history in server memory and
  clear it on restart.

## [0.15.0] - 2026-10-01 @ 03:42

### Added

- Discover manually added applications during inventory scans using
  `/opt/prod/<lowercase-name>/<lowercase-name>/constants/<Name>.py` and a literal
  `VERSION`; show detected deployments in Inventory and Applications.
- Add Re-Scan Applications to check application installations on inventoried
  hosts through the existing scanner worker.

- Add `DCmdb.BASE_INSTALL_DIR` with the value `/opt/prod`.

- Add an Add Application panel beneath Deployed Applications, saving a named
  SoftwareSystem without a host or deployment.

## [0.14.2] - 2026-09-30 @ 19:27

### Changed

- Make the CMDB logo and favicon background transparent.

## [0.14.1] - 2026-09-30 @ 19:22

### Added

- Added a logo.

### Changed

- Use cmdb.png as the application header logo and favicon, and as the
  documentation site's logo and favicon; include the image in service deployments.

- Make the Applications table's Install Directory heading sort ascending or
  descending like the other columns.

## [0.14.0] - 2026-09-30 @ 19:01

### Changed

- Simplify Applications to one table with Host, Application, Version, and Install
  Directory, with reversible sorting on the first three column headings.

- Remove the coding guidelines' restriction on assistant Git operations and
  release scripts, allowing them within the authorized workflow.

## [0.13.6] - 2026-09-30 @ 18:53

### Added

- Add an Expand All / Collapse All toggle to Deployed Applications, keeping its
  label synchronized with individual machine sections and resetting on page load.

## [0.13.5] - 2026-09-30 @ 18:48

### Added

- Add Applications navigation between Inventory and Patching, with a Deployed
  Applications table showing existing software deployments grouped by machine
  in the same collapsible layout as Live Databases.

- Add Re-Scan beneath the selected inventory machine's header to refresh that
  host through discovery, OS detection, and SSH inventory, retaining selection.

## [0.13.4] - 2026-09-29 @ 05:19

### Changed

- Simplify patching uptime to a single unit: seconds, minutes, hours, or days,
  with one decimal place for hours and days.

## [0.13.2] - 2026-09-29 @ 04:47

### Changed

- Show machines absent from the latest successful discovery in muted red, including
  their software boxes; selection retains the orange border.
- Match selected inventory machine borders to the page's orange border color.
- Use one per-host Status cell for the latest patch, schedule, or uptime message. New
  messages replace it immediately; unchanged polling does not restore old results.

## [0.13.1] - 2026-09-28 @ 19:37

### Changed

- Move Live Databases backup messages into a Status column beside Actions.

## [0.13.0] - 2026-09-28 @ 19:25

### Added

- Add confirmed database deletion to Live Databases, protecting cmdb and system
  databases, disabling its schedule, and retaining backup history and files.

### Changed

- Move Update beside Cron Schedule in an unlabeled column; retain Actions for
  Backup Now and Delete.

## [0.12.7] - 2026-09-28 @ 19:07

### Added

- Add the same 20-character Cron Schedule field to Live Databases. Backup schedules
  now save their own cron expressions, defaulting to daily at noon.

### Upgrade instructions

Before upgrading an existing installation, run once in the CMDB database:

```sql
ALTER TABLE BackupSchedule
    ADD COLUMN expression VARCHAR(255) NOT NULL DEFAULT '0 12 * * *';
```

Existing schedules retain daily noon timing. Fresh installations need no manual change.

### Changed

- Use one 20-character-wide text box under Cron Schedule, with a single header
  row. Keep Machine, Uptime, and Enabled on one line and let Status wrap.

## [0.12.5] - 2026-09-28 @ 18:58

## [0.12.3] - 2026-09-28 @ 18:53

### Changed

- Align all Debian host column headers along the bottom of one row, with Schedule
  alone above its five fields.
- Keep Debian host Machine, Uptime, and Enabled headers and cells on one line,
  allowing Status to wrap into the remaining space.
- Show cron field labels once in a shared second header row, with each host's
  dropdowns aligned beneath them.

## [0.12.2] - 2026-09-28 @ 18:47

### Changed

- Run apt-get autoremove after patch upgrades and before rebooting; stop before
  reboot if package cleanup fails.
- Replace the patch cron text field with five labeled dropdowns and remove the
  explanatory text. Existing backend validation handles invalid selections.

## [0.12.0] - 2026-09-28 @ 18:33

### Added

- Add per-host patch scheduling with Enabled, a five-field cron expression, and
  Update. Cron queues jobs independently of the web service using the existing
  patch runner; disabling removes the cron entry.
- Add PatchSchedule storage, created by the normal installer.

### Changed

- Refresh uptime automatically when the Patching page opens, retaining manual refresh.

## [0.11.4] - 2026-09-28 @ 18:14

### Added

- Add Uptime to Debian Hosts and a bottom-left Refresh Uptime button that reads
  current uptime through SSH without storing it in the database.

## [0.11.3] - 2026-09-28 @ 18:02

### Changed

- Update patching status and report cells in place while polling, preserving rows
  and visible results during requests to prevent flicker.

## [0.11.2] - 2026-09-28 @ 17:53

### Changed

- Remove stored apt output from patch jobs and Patch Report; retain status, timing,
  and errors. Remove the Patch output column from the schema.

### Upgrade instructions

After upgrading the application, run this once in the existing CMDB database to
remove the old apt output column and its stored contents:

```sql
ALTER TABLE Patch DROP COLUMN output;
```

Fresh installations already omit this column and need no manual change.

## [0.11.1] - 2026-09-28 @ 17:46

### Changed

- Simplify Debian Hosts to Machine, Actions, and Status columns.
- Add a separate Patch Report panel with the most recent 100 runs, elapsed time,
  outcomes, errors, and expandable package output.

## [0.11.0] - 2026-09-28 @ 17:23

### Added

- Add Patching with Debian hosts and Patch Now, backed by an independent runner
  that records updates, reboots every successfully patched host, and verifies
  its return. Resume reboot verification after the CMDB host itself restarts.

## [0.10.4] - 2026-09-28 @ 16:25

### Changed

- Move Scan Filesystem to the bottom-left corner of the Backup Vault panel.
- Move Refresh and its timestamp inside the inventory panel, below the machine view.
- Match Backup Vault's Scan Filesystem and Delete Record buttons to Inventory's
  Refresh button styling.

## [0.10.3] - 2026-09-28 @ 16:19

### Changed

- Show filenames in Backup Vault with the configured backup directory above the table.
- Add Scan Filesystem to mark recorded dumps Found or Missing without checksum checks.
  Missing rows offer Delete Record, which rechecks absence and removes only the record.

## [0.10.1] - 2026-09-28 @ 16:04

### Changed

- Store new database dumps in `<host>/db/<database>/`, creating the directory
  as needed and keeping temporary files alongside the final dump.
- Remove the Frequency column from Live Databases; scheduled backups remain
  fixed to daily at noon.

## [0.10.0] - 2026-09-28 @ 15:57

### Added

- Enable Update to persist backup settings and manage daily noon cron entries
  through python-crontab, preserving unrelated jobs. Disabling removes the cron
  entry; retention is saved without deleting files.
- Add the independent venv-based cmdb-backup.py runner, using shared backup code
  to execute and record jobs without the web service. Install cron support and
  give the service account read access to its database configuration.

### Changed

- Stop marking running backups failed when the web service restarts or reads
  backup records, since jobs can now run independently under cron.

## [0.9.11] - 2026-09-28 @ 15:27

### Changed

- Combine the application and view names into one heading: CMDB Inventory or
  CMDB Backups, with matching text sizes.

## [0.9.10] - 2026-09-28 @ 15:24

### Added

- Show Inventory beneath the CMDB subtitle on the homepage, matching the Backups
  heading's size and placement.

### Changed

- Move the Backups heading into the CMDB title box below the subtitle, preserving
  its size and removing its separate box.

## [0.9.9] - 2026-09-28 @ 15:19

### Changed

- Split the Backups view into separate Backups, Live Databases, and Backup Vault
  boxes, with the backup files table inside Backup Vault.
- Replace the Backup Files FQDN column with Filename, showing the full path
  using the configured backup directory and each recorded dump pathname.

## [0.9.8] - 2026-09-28 @ 15:13

### Added

- Show Elapsed Time (`HH:MM:SS`) for backup files, measured from the CMDB job's
  start through completion, including queue time and preparation.
- Add a Backup Files table beneath Live Databases, showing successful backups
  newest first with backup time, machine, database, and FQDN. Refresh it after
  a manual backup completes.

### Changed

- Use “Processing backup job...” while a backup is starting or running.
- Simplify dump filenames to `YYYY-MM-DD_HH:MM:SS`, removing fractional seconds
  and the attempt-ID suffix.

## [0.9.7] - 2026-09-28 @ 14:52

### Fixed

- Remove the NFS filesystem check so backups also work on Wintermute's local
  backing storage. Keep temporary files in the destination directory.

## [0.9.6] - 2026-09-28 @ 14:46

- Corrected backup target directory.

## [0.9.4] - 2026-09-28 @ 14:43

### Added

- Implement Backup Now with asynchronous bookkeeping, host-local MariaDB dumps
  directly into the NFS backup directory, SHA-256 checksums, status polling, and
  Last Backup updates. Keep temporary files beside final dumps. Add agent dump
  privileges and local service write access; scheduling and retention remain deferred.
- Add the application-specific Backup entity and table for individual attempts,
  with inventory references, timestamps, status, file path, size, SHA-256 checksum,
  and failure details. Enforce consistent completion records independently of schedules.
- Add the application-specific BackupSchedule table and entity, with one policy
  per ModelElement, disabled by default, daily frequency, and validated retention
  choices. UI persistence and backup execution remain pending.

## [0.9.3] - 2026-09-28 @ 13:51

### Added

- Add per-database Enabled checkboxes, fixed Daily frequency, and Retention
  choices of 1 week, 2 weeks, 1 month, or Forever. Add disabled Update and
  Backup Now buttons pending backup implementation; settings are not yet saved.

## [0.9.2] - 2026-09-28 @ 13:00

### Changed

- Remove the horizontal rule beneath the main page title.
- Group database backups into collapsed host sections with user database counts,
  such as `Islands - 1 DB`. Exclude `mysql`, `information_schema`,
  `performance_schema`, and `sys` from backup lists and counts.

## [0.9.0] - 2026-09-28 @ 12:51

### Added

- Add a top-right Backups link that replaces the inventory panel with a database
  table showing Host, Database, and placeholder Last Backup values (`---`).
  The link changes to Inventory to return to the existing homepage.

## [0.8.1] - 2026-09-28 @ 11:52

### Changed

- Group MariaDB database names with user databases first, followed by a horizontal
  rule when present, then system databases on their own lines.

## [0.8.0] - 2026-09-28 @ 11:47

### Added

- Show stored database names as the final Database(s) row in MariaDB details,
  one name per line.

### Removed

- Remove Deployed Components from machine details and Codename from MariaDB
  details in the GUI.

## [0.7.5] - 2026-09-28 @ 11:38

### Changed

- Clicking a machine or its software loads all its software details below the
  expanded machine details, OS first and MariaDB next. Software sections have
  collapsible headings and start collapsed.

### Removed

- Remove the Edit button and hostname editing controls from machine details.

## [0.7.4] - 2026-09-28 @ 11:28

### Added

- Add a collapsible Machine heading to the left details panel; clicking a machine
  expands its details. Clicking nested software shows Software System details
  below the machine in the same panel.

## [0.7.3] - 2026-09-28 @ 11:16

### Removed

- Remove the Machine dropdown; select machines by clicking their graph nodes.

## [0.7.2] - 2026-09-28 @ 10:52

### Changed

- Shorten MariaDB graph labels to the release number (for example, `MariaDB
  11.8.6`), retaining the complete version in the database.

## [0.7.1] - 2026-09-28 @ 10:48

### Fixed

- Explicitly disable TLS for agent provisioning and inventory connections over
  local MariaDB Unix sockets, fixing certificate verification failures during
  installation and remote discovery. After updating the checkout, rerun
  `sudo scripts/install.sh` to resume the interrupted installation.

## [0.7.0] - 2026-09-28 @ 10:45

### Added

- Display MariaDB below the OS inside each machine, using the same rounded
  software box style regardless of discovery order.

- Collect MariaDB server version, data directory, and database names through
  the local/SSH agent path. Store software releases, DataManager deployments,
  and linked Schema records, reusing identities on repeated scans.

- Prepare database inventory storage with ModelElement.name, Package, Schema,
  DataManager, and the CWM DataManagerDataPackage association. Keep inherited
  fields on their parents and preserve both many-valued association ends.

- Provision MariaDB `cmdbagent@localhost` with Unix-socket authentication and
  `SHOW DATABASES` access. SSHDb checks existing agents and provisions remote
  accounts through root SSH when needed; install/upgrade handles the local account.
- Keep repeatable database-account SQL in `schema/cmdbagent.sql`.

### Installation

Use uninstall/install for this release's fresh schema; no record migration is
provided. Installation also provisions the local database agent. Refresh provisions remote MariaDB
agents where root SSH and local MariaDB administrative access are available.
Refresh populates MariaDB software and database inventory. Backup jobs remain future work.

## [0.6.3] - 2026-09-28 @ 10:09

### Changed

- Use `cmdbagent` for managed-host inventory, retaining local `cmdb` as the
  service/key owner. Install and upgrade provision the local agent and sudo rule.

### Added

- One-time remote cleanup script to delete legacy `cmdb` accounts and homes,
  skipping the local server and reporting per-host failures.

### Upgrade instructions

Run these commands in order from the development checkout:

```sh
sudo scripts/upgrade.sh
sudo /opt/prod/cmdb/.venv/bin/python -B scripts/cleanup-remote-cmdb.py
```

Upgrade provisions the local `cmdbagent` account and switches inventory access
to that identity. The scanner provisions remote `cmdbagent` accounts as needed.

The one-time cleanup reads discovered hosts from the database, connects as root
using the existing CMDB SSH key, and removes each legacy remote `cmdb` account
and its home directory. Remote root must authorize that key. The local machine
is skipped, preserving its `cmdb` service account, SSH key, and home.

Review the per-host results. Failed removals produce a nonzero exit status;
resolve those failures and rerun the cleanup as needed. Already-removed
accounts are skipped safely.

## [0.6.1] - 2026-09-28 @ 09:43

### Added

- Show deployed software as rounded rectangles inside machine nodes, with
  labels such as `Debian (trixie) 13.6` from SoftwareSystem and its codename tag.

### Changed

- Hide Site in the machine details display.

- Set SoftwareSystem supplier to `Debian` for host releases with `ID=debian`.

## [0.6.0] - 2026-09-28 @ 09:30

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
