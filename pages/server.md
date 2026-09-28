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
| `/health` | HTTP 200 JSON identifying `cmdb-server`; checks HTTP availability without querying MariaDB. |
| `/ready` | Queries MariaDB; HTTP 200 when connected, HTTP 503 on a database error. |

Database errors are logged to the service journal; the HTTP response contains
only a short status. Each readiness request opens and closes its own database
connection. The server foundation has no inventory editing endpoints yet.

The main panel fills the remaining window below the title. It loads database
records when the page opens; use Refresh at the bottom left to reload the page
and see subsequent scan updates.
Nodes show the hostname and IP address, or just the address when unnamed.
Click a node or use the machine selector to see its fields and UTC timestamps.
An empty inventory and an unavailable database show distinct status messages.

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
host and available on `PATH`; the Python package does not install that executable.

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

The server starts a background machine scanner immediately, then waits
`DCmdb.SCAN_INTERVAL_SECONDS` (default `300`) after each scan before repeating.
`SCAN_TARGET` defaults to the observed LAN, `192.168.0.0/24`;
`SCAN_TIMEOUT_SECONDS` defaults to `30`. These settings are in
`cmdb/constants/DCmdb.py`.

The worker uses host discovery (`-sn`) and upserts responding hosts into
`machines`. Each observation refreshes `updatedOn`, even when no attributes
change; `createdOn` stays fixed. A discovered hostname updates `hostName`;
missing hostnames preserve the existing value. Existing `site` and
`deployedComponent` values and machines absent from a scan are retained.

The worker prints its startup message to the journal. Scan and database failures
are retried on the next interval without logging. It owns a database connection
per scan and stops with the server, waiting for any active scan to finish or
reach its timeout.
