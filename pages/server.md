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
| `POST /api/machines/hostname` | Saves `hostName` for an existing `ipAddress` and returns the updated machine. |
| `POST /api/scan` | Signals the scanner worker and returns HTTP 202 with the scan ID; shares an active scan. |
| `GET /api/scan` | Reports scan progress and completion, or HTTP 503 if the worker is unavailable. |
| `/health` | HTTP 200 JSON identifying `cmdb-server`; checks HTTP availability without querying MariaDB. |
| `/ready` | Queries MariaDB; HTTP 200 when connected, HTTP 503 on a database error. |

Database errors are logged to the service journal; the HTTP response contains
only a short status. Each readiness request opens and closes its own database
connection.

The main panel fills the remaining window below the title. It loads database
records when the page opens. Refresh at the bottom left wakes the existing
scanner worker, waits for the scan and database writes to finish, then reloads
the page. It shows Scanning while waiting and an error if the scan fails.
Requests during an active scan share that scan; scans never overlap.
Nodes use bold white 16px labels. Named machines have dark green rounded
rectangles of size 160 × 80 when empty; unnamed machines have grey circles.
Machines with deployed software expand into rounded containers with the machine
name above nested software rectangles. Software labels include the subtype,
codename when present, and version, such as `Debian (trixie) 13.6`.
MariaDB appears in a matching box below the OS, regardless of discovery order.
Machines remain arranged in a circle. Clicking a machine or any inner software
rectangle loads the machine and its available software systems in the left panel.
The OS appears first, then MariaDB. Each software section starts collapsed with
a heading such as `Software System: Linux` or `Software System: RDBMS`; click
the heading to expand its fields.
Selection lightens the containing machine’s color.
Named machines show
only the unqualified hostname with its first letter capitalized; unnamed machines
show their IP address. Details retain the full hostname and IP address.
Click a node to see its fields and timestamps in
browser-local time (`YYYY-MM-DD HH:MM:SS`)
in a key/value table left of the graph (above it on narrow screens).
The `Machine: Sally` (or IP address) heading collapses the machine section to
just its heading. Clicking a machine or its software expands the machine details
and resets its software sections to collapsed.
An empty inventory and an unavailable database show distinct status messages.
Detail labels come from `DLabel.ATTRIBUTES` in `cmdb/constants/DLabel.py`,
for example `ipAddress` displays as IP Address and `hostName` as Host Name.
The mapping affects presentation only; model attributes, API keys, and database
columns retain their original names.

Machine details are read-only. Successful SSH discovery populates the hostname
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

The server starts `cmdb/activity/MachineScanner.py` immediately and owns its
startup and shutdown. The background activity waits
`DCmdb.SCAN_INTERVAL_SECONDS` (default `300`) after each scan before repeating.
`SCAN_TARGET` defaults to the observed LAN, `192.168.0.0/24`;
`SCAN_TIMEOUT_SECONDS` defaults to `30`. These settings are in
`cmdb/constants/DCmdb.py`.

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
stop timeout is 210 seconds to allow the active scan to finish or time out.

The scanner then runs the [SSH follow-up]({{ site.baseurl }}{% link pages/ssh.md %}#scanner-follow-up)
to test `cmdb` access, provision it through root where possible, and retrieve
the remote hostname. This also runs when OS detection finds no match or times
out. Refresh waits for the SSH stage too; each host has bounded connection and
command timeouts. SSH failures are isolated to that host and preserve its data.

The worker prints its startup message to the journal. Scan and database failures
are retried on the next interval without logging. It owns a database connection
per scan and stops with the server, waiting for any active scan to finish or
reach its timeout.
