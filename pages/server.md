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
