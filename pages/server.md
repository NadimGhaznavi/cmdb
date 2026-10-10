---
title: CMDB Server
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

`cmdb-server.py` starts the CMDB HTTP server on `0.0.0.0:14444`. It follows
MyCount's standalone control-server pattern and uses the same MariaDB
connection and transaction layer, adapted to the `cmdb` package.

| Endpoint | Behavior |
| --- | --- |
| `/` | Boxed machine graph with clickable nodes and stored machine details. |
| `/api/machines` | Reads machines from MariaDB as JSON; HTTP 503 when the database is unavailable. |
| `POST /api/applications` | Registers a named SoftwareSystem and queues its discovery; returns HTTP 201 with id, name, and scanId. |
| `DELETE /api/applications/<id>` | Removes one registered SoftwareSystem and its application deployments; returns HTTP 404 for a missing ID. |
| `POST /api/applications/scan` | Queues application discovery on inventoried hosts; returns HTTP 202 with scanId. |
| `GET /api/backups` | Lists MariaDB user databases and declared application directory/database targets, policies, latest attempts, and last successful completion times. |
| `POST /api/backups` | Accepts a `modelElement` ID and returns HTTP 202 with a `backupId`; duplicate active requests share the attempt. |
| `GET /api/backups/<id>` | Returns the recorded attempt and its status, file metadata, and error. |
| `GET /api/patching/report` | Lists the most recent 100 patch jobs, newest first, with elapsed time and results. |
| `GET /api/patching/hosts/<id>/uptime` | Reads current uptime through SSH for an inventoried Debian host. |
| `GET /api/patching/hosts` | Lists Debian hosts and their latest patch job status. |
| `POST /api/patch-schedules` | Saves a machine's enabled flag and five-field cron expression. |
| `POST /api/patching` | Queues a patch-and-reboot job for a machine ID; returns HTTP 202 and jobId. |
| `DELETE /api/databases/<id>` | Drops an inventoried user database after exact-name confirmation; protects cmdb and system databases. |
| `GET /api/backups/files` | Lists successful database dumps and directory tarballs newest first with completion time and inventory names. |
| `POST /api/backups/files/scan` | Checks recorded files for existence, returning Found or Missing without checksums. |
| `DELETE /api/backups/files/<id>` | Deletes a successful backup's dump file and then its Backup record; also cleans up records for missing files. |
| `POST /api/backup-schedules` | Saves modelElement, enabled, cron expression, and retention; creates or removes the schedule's cron entry. |
| `DELETE /api/backup-schedules/<id>` | Removes a policy and its cron entry, retaining backup history. |
| `POST /api/machines/hostname` | Saves `hostName` for an existing `ipAddress` and returns the updated machine. |
| `POST /api/machines/environment` | Saves `DeploymentEnvironment` for a machine ID; Unclassified removes the tag. |
| `GET /api/discovery` | Returns the configured network and saved discovery policy, disabled by default. |
| `POST /api/discovery-schedules` | Saves Enabled and a five-field cron expression and updates its cron entry. |
| `POST /api/scan` | Queues an Inventory workload and returns HTTP 202 with its scanId. |
| `GET /api/scan` | Reports scan progress and completion, or HTTP 503 if the worker is unavailable. |
| `/status-messages` | Reads shared in-memory status history as JSON without querying MariaDB. |
| `/health` | HTTP 200 JSON identifying `cmdb-server`; checks HTTP availability without querying MariaDB. |
| `/ready` | Queries MariaDB; HTTP 200 when connected, HTTP 503 on a database error. |

Database errors are logged to the service journal; the HTTP response contains
only a short status. Each readiness request opens and closes its own database
connection.

Every screen includes a Status Messages table below its main panel, with a header,
five visible rows, and scrollable history. It polls shared server history every two
seconds and shows inventory and application scan starts, completions, and failures.
Application scan results identify hosts by their unqualified, lowercase hostname
when available, or by IP address otherwise.
Each history entry contains `timestamp` (the recording time in UTC), `source`
(the full name of the module calling `append()`), and `message`. The table displays
Timestamp, Source, and Message columns as plain text. Timestamps use the browser's
local time in `YYYY-MM-DD HH:MM:SS` format. History stays in memory and clears when the
server restarts; it is not written to MariaDB or disk.

The homepage keeps the machine inventory graph. The top navigation links to
Inventory, Applications, Patching, and Backups, in that order.
The header logo and browser favicon use `pages/images/cmdb.png`, also used by
the documentation site. Clicking the application logo returns to Inventory.
Applications shows one Deployed Applications table for existing software deployments,
including Debian and MariaDB, with Host, Application, Version, and Install Directory
columns. Both Deployed Applications and Registered Applications start collapsed,
showing only their heading titles. Click a heading to expand or collapse its table
and controls. The deployed table starts sorted by Host ascending. Click any column heading
to sort ascending; clicking the active heading reverses the order. Version sorting
compares numeric parts naturally (for example, 11.9 precedes 11.10). An arrow
marks the active sort direction, which is retained when reopening the page.
The path is the recorded deployment path: `/` for the OS convention and
the data directory for MariaDB. Below the deployed table, Registered Applications
lists every stored SoftwareSystem with ID, Application Name, Type, Subtype,
Supplier, Version, and Actions, including definitions without deployments. Each
row has a Delete button with confirmation. Deletion affects only that ID, even
when names match, and refreshes both application tables. It removes the software
definition and its application deployments from CMDB without uninstalling
anything on hosts. Applications can be manually re-added; OS and MariaDB records
can be rediscovered by inventory scans. Named applications need a registered
definition before application discovery can find them again.
For database software, CMDB retains standalone components, database managers,
and schemas to preserve backup history and files, and disables related backup
schedules and removes their cron entries. Rediscovery reuses the database manager
and schema IDs; schedules remain disabled until explicitly enabled again.
Unexpected dependent inventory prevents deletion with HTTP 409, and database or
cron errors return HTTP 503. Beneath this
table, an inline Application Name field and Add Application button save a
SoftwareSystem definition and queue discovery for that application across all
inventoried hosts.
The form waits for discovery and pruning before refreshing both application
tables. Names are trimmed and must contain 1–255 characters without control
characters. Discovery records deployments when an installation is found; an
undeployed definition is pruned and reported in Status Messages. Browser Back
and Forward also switch these views.
Re-Scan Applications checks named application definitions on all inventoried hosts,
without running Nmap. It uses the same worker and `/api/scan` progress reporting
as inventory scans, displays progress or failure, and reloads the page after success.
Inventory scans also check applications after collecting each host’s details
and MariaDB inventory.
See [application discovery]({{ site.baseurl }}{% link pages/software-deployment.md %}#application-discovery)
for the installation convention.
The Backups page starts with an Application panel above Databases. It starts
collapsed and groups declared directory and database backup targets by host and
application. Each target uses the same scheduling and manual backup controls as
Databases. Directory archives go under `<host>/files/`; database paths stay under
`<host>/db/`. Declared database rows share their existing database policy and history.
The Databases panel starts collapsed; click its heading to expand or collapse it.
It groups stored databases into collapsible host sections,
initially collapsed, with headings such as `Islands - 1 DB` or
`Neuromancer - 2 DBs`. Host headings use the same short, capitalized hostname
as the inventory graph, or the IP address when unnamed. Each section contains
Database, Enabled, Cron Schedule, Retention, Last Backup, and Actions columns.
The default cron expression runs daily at noon. For a new policy, Enabled starts unchecked, and Retention offers
1 week (the default), 2 weeks, 1 month, and Forever. Update persists these settings
and creates or removes the configured cron job. Existing settings are loaded when the
page opens. Retention deletion remains unimplemented.
Backup Now runs a manual backup independently of Enabled, displays
progress or failure, and updates Last Backup after success. Wide tables scroll
horizontally on narrow screens. See [manual backups]({{ site.baseurl }}{% link pages/backups.md %}).
The system databases `mysql`,
`information_schema`, `performance_schema`, and `sys` are excluded from both
the rows and counts. DBMS hosts without user databases show `0 DBs` and an empty
state when expanded. Last Backup displays `---` until the first successful backup.
Browser Back and Forward also switch
views. The scan button and refresh timestamp are shown only on Inventory.

Inventory groups machines into bordered, collapsible boxes stacked in this order:
Production, Quality Assurance, Development, and Unclassified. All boxes start expanded
and show `Machines (XX)` beside their title, including when collapsed. Each box uses
a responsive grid and shows an empty message when it has no machines. Missing or
unrecognized deployment environments appear under Unclassified. Selecting a machine reveals a separate details box on the left; on
narrow screens the details box appears above the graph. The graph box includes
its loading or error message, Re-Scan Network button, and last-refresh timestamp. It loads
database records when the page opens. Re-Scan Network at the bottom left wakes the existing
scanner worker, waits for the scan and database writes to finish, then reloads
the page. It shows Scanning while waiting and an error if the scan fails.
Stored inventory stays interactive during scans: machines and software can be
selected, details expanded, environments updated, and other pages opened.
Only the scan buttons are disabled while a browser-requested scan is pending.
Requests enter a FIFO queue; one workload runs to completion before the next starts.

Re-Scan beneath a selected machine's header runs the same discovery, OS, and SSH
inventory steps for that host alone, then reloads with the machine selected.
Requests made during an active workload wait in the same queue.
Other machines' reachability results are preserved by a single-host scan.

When an application is selected, its Inventory detail sidebar shows a
`Database(s):` row above the Component table if discovered databases are present.
Multiple names are comma-separated; applications without databases omit the row.
The Component table shows declared filesystem components; MariaDB client
providers supply database relationships and are omitted from that table.

The app uses MyCount’s warm dark theme: brown backgrounds, cream text, orange
links and focus outlines, and subtle brown panel and table borders. Nodes use
bold 24px labels with contrasting text.
Named machines have dark brown rounded rectangles of size 160 × 80 when empty;
unnamed machines have cream circles.
Machines with deployed software expand into rounded containers with the machine
name above nested software rectangles. Software labels include the subtype,
codename when present, and version, such as `Debian (trixie) 13.6`.
MariaDB appears in a matching box below the OS, regardless of discovery order.
Machines are arranged in a grid within their environment box. Clicking a machine or any inner software
rectangle loads the machine and its available software systems in the left panel.
The OS appears first, then MariaDB. Each software section starts collapsed with
a heading such as `Software System: Linux` or `Software System: RDBMS`; click
the heading to expand its fields. MariaDB details end with a Database(s) row,
listing stored Schema names for that deployment, one per line (or a dash when
none are recorded). User databases appear first, followed by a horizontal rule
when any are present, then system databases: `mysql`, `information_schema`,
`performance_schema`, and `sys` when recorded.
Selection turns a reachable machine blue with cream text. Unreachable machines
use muted red with cream text and a blue border when selected. Software boxes
use a lighter shade of their machine's background, including blue when selected
and muted red when unreachable.
Named machines show
only the unqualified hostname with its first letter capitalized; unnamed machines
show their IP address. Details retain the full hostname and IP address.
Click a node to see its fields and timestamps in
browser-local time (`YYYY-MM-DD HH:MM:SS`)
in a key/value table left of the graph (above it on narrow screens).
The `Machine: Sally` (or IP address) heading collapses the machine section to
just its heading. Clicking a machine expands the machine details and resets its
software sections to collapsed. Clicking a software box highlights that box and
shows only that software system's expanded details, without the machine section.
Deselecting the machine or software hides the details sidebar.
When an application has named deployed components, its details include a
Component / Path table. Each path shows only the final directory name as a
filesystem link; hovering over it displays the full absolute path.
Components are grouped under their application on the same machine.
An empty inventory and an unavailable database show distinct status messages.
Detail labels come from `DLabel.ATTRIBUTES` in `cmdb/constants/DLabel.py`,
for example `ipAddress` displays as IP Address and `hostName` as Host Name.
The mapping affects presentation only; model attributes, API keys, and database
columns retain their original names.

The environment dropdown loads the selected machine's saved classification.
Update sends a JSON object with `machine` (the numeric Machine ID) and
`environment` (`dev`, `qa`, `prod`, or `unclassified`). Saving creates or updates
the `DeploymentEnvironment` TaggedValue on that machine's ModelElement;
Unclassified deletes it. The API returns the saved `environment`, HTTP 400
for invalid input, 404 for a missing machine, or 503 for database failure.
The controls show save progress and results; discovery preserves the tag.
A successful save moves the machine to its environment box and updates both
group counts immediately, retaining the selected machine and each box’s collapsed state.

Other machine details are read-only. Successful SSH discovery populates the hostname
reported by the machine.

[Cytoscape.js](https://js.cytoscape.org/) 3.34.3 and its MIT license are bundled
under `cmdb/server/static/vendor/`, so the graph needs no CDN connection.

## Service status

```sh
systemctl status cmdb-server.service
journalctl -u cmdb-server.service -f
curl -i http://127.0.0.1:14444/health
curl -i http://127.0.0.1:14444/ready
```

## Development

For Python server development, create a virtual environment and install its
dependencies. These are independent of the documentation site, which GitHub
Pages builds.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest discover -s tests -v
```

Database integration tests are skipped unless `CMDB_TEST_DB_SOCKET` points to
a test MariaDB instance with local root access. They create and remove their
own randomly named databases. For example, with a disposable instance already
running at `/tmp/cmdb-test/db.sock`:

```sh
CMDB_TEST_DB_SOCKET=/tmp/cmdb-test/db.sock .venv/bin/python -B -m unittest discover -s tests -p test_software_deployment_db.py -v
```

To start manually, provide `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and
`DB_PASSWORD` in the process environment, then run:

```sh
.venv/bin/python -B cmdb-server.py --host 127.0.0.1 --port 14444
```

The server validates the database environment at startup. `/ready` verifies
the actual connection. `DbMgr` owns connections, cursors, bound SQL execution,
and transactions; application code should use domain interfaces built on this
layer as inventory features are added.

## Network scans

`cmdb/interface/Nmap.py` wraps
[python-nmap](https://pypi.org/project/python-nmap/). Install the Python
dependencies above and ensure the `nmap` executable is installed on the scanning
host at `/usr/bin/nmap`; the Python package does not install that executable.
Scans use sudo through python-nmap. Installation grants the `cmdb` account
passwordless root access to Nmap with unrestricted arguments, enabling LAN ARP
discovery and MAC collection. See
[installation]({{ site.baseurl }}{% link pages/installation.md %}) for the sudoers
rule. Manual development scans require sudo permission for the invoking user.

The following uses an example LAN address, not the current network configuration:

```python
from cmdb.interface.Nmap import Nmap

scanner = Nmap()
result = scanner.scan("192.168.1.10", ports="22,80,443", timeout=60)
hosts = result["scan"]
```

`scan()` returns python-nmap's result dictionary. It accepts Nmap target and
port syntax, optional `arguments` (default `-sV`), and a timeout in seconds
(default `0`, unlimited). Library errors propagate to the caller. Use a separate
instance per worker thread.

The server starts `cmdb/activity/InventoryCoordinator.py` immediately and owns its
startup and shutdown. The background activity waits for explicit requests;
it does not scan at startup, on page load, or on an internal timer.
[Discovery]({{ site.baseurl }}{% link pages/discovery.md %}) manages periodic scans
through cron independently of the web service.
`SCAN_TARGET` defaults to the observed LAN, `192.168.0.0/24`;
`SCAN_TIMEOUT_SECONDS` defaults to `30`. These settings are in
`cmdb/constants/DCMDB.py`.

The worker uses host discovery with DNS resolution disabled (`-sn -n`) and
upserts responding hosts into
`Machine`. Each observation refreshes `updatedOn`, even when no attributes
change; `createdOn` stays fixed. Nmap does not resolve or populate hostnames.
When Nmap reports a MAC address, the worker stores it in `macAddress`, shown in
the details table. Scans without a MAC preserve any previously stored address.
The SSH follow-up also reads the interface owning the scanned IP to populate
its MAC. For the local machine, the SSH interface runs those commands directly,
so collection does not require a local SSH server or Nmap-reported MAC.
The Nmap pass preserves existing hostnames, including manual edits. Existing `site`
values and machines absent from a scan are retained.

Inventory shows machines absent from the latest successful discovery in
red, including their software boxes. Selected machines use a blue border.
Reachability is held in memory until restart; failed discovery scans preserve
the previous result. Hosts outside the scanned subnet and hosts awaiting the
first successful scan keep their usual colors.

After committing machine discovery and closing its database connection, the
worker runs a separate OS scan against the responding IPs using
`-O -n --osscan-limit --max-os-tries 1`. It uses Nmap's default TCP port set;
port results are not stored. `OS_SCAN_TIMEOUT_SECONDS` defaults to `180`.
[Nmap OS detection](https://nmap.org/book/man-os-detection.html) works best with
an open and a closed TCP port; `--osscan-limit` skips targets without both.
The complete refresh includes both passes and can take longer than discovery
alone. If OS scanning fails, the machine updates remain committed and the
refresh reports a scan failure. OS writes use a separate transaction.

The subsequent hostname/MAC follow-up also reads `os-release` through the SSH
interface. Valid host-reported releases update the same OS deployment after
Nmap, using the existing SoftwareSystem and Component mapping.

OS classifications populate the
[software deployment model]({{ site.baseurl }}{% link pages/software-deployment.md %}).
Missing or inconclusive results preserve existing OS records. The service's
stop timeout is 3900 seconds to allow the active scan and a bounded backup to finish.

For each responding host, the coordinator runs the [SSH follow-up]({{ site.baseurl }}{% link pages/ssh.md %}#scanner-follow-up)
to test `cmdbagent` access, provision it through root where possible, and collect
host details. It then collects MariaDB inventory and checks registered applications
before moving to the next host. This also runs when OS detection finds no match or times
out. Refresh waits for the SSH stage too; each host has bounded connection and
command timeouts. SSH failures are isolated to that host and preserve its data.

The worker prints its startup message to the journal. Scan and database failures
are reported for that request; another scan requires a new request or cron run.
It opens short database transactions to apply observations, closes connections
before collecting more data, and stops with the server. Pending requests and
reachability results are held in memory and are lost on restart.

## Inventory coordination

`InventoryCoordinator` owns triggering, the FIFO request queue, sequencing,
persistence, status messages, and pruning. The source modules in
`cmdb/activity/sources/` collect observations and do not schedule work or write
inventory records:

| Source | Observation |
| --- | --- |
| NetworkSource | Responding IPs and available MAC addresses |
| NmapOSSource | Unambiguous Nmap OS classifications |
| HostSource | Hostname, interface MAC address, and host-reported OS release |
| MariaDBSource | MariaDB version, data directory, and schema names |
| ApplicationSource | One application's installed version on one host |

Cron runs full Inventory in its own process. The network and
single-machine buttons request Inventory with the corresponding host scope.
Re-Scan Applications checks all registered application names on all stored
machines. Add Application queues a check of that new definition on all stored
machines, without network discovery. Every accepted request gets its own scan ID.
`GET /api/scan?scanId=ID` reports progress with the requested workload's outcome;
the worker keeps the most recent 100 completion outcomes in memory.

Every workload ends with automatic pruning, including failed or empty scans.
SoftwareSystems with no deployed components are removed along with their unused
Components, tags, and inherited records. Each removal appears in Status Messages
with the software name and version when available. A newly added definition is
protected until its own queued discovery attempt finishes; if no deployment was
recorded, it is then pruned. Existing deployments remain when software is not
detected or a host cannot be read.
