---
title: CMDB Server
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

`cmdb-server.py` starts the CMDB HTTP server on `0.0.0.0:14444`. It follows
MyCount's standalone control-server pattern and uses the same MariaDB
connection and transaction layer, adapted to the `cmdb` package.

| Endpoint | Behavior |
| --- | --- |
| `/` | CMDB landing page and documentation link. |
| `/health` | HTTP 200 JSON identifying `cmdb-server`; checks HTTP availability without querying MariaDB. |
| `/ready` | Queries MariaDB; HTTP 200 when connected, HTTP 503 on a database error. |

Database errors are logged to the service journal; the HTTP response contains
only a short status. Each readiness request opens and closes its own database
connection. The server foundation has no inventory editing endpoints yet.

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
