---
title: Server Installation
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

CMDB follows MyCount's control-server installation pattern: a dedicated Linux
account, a local MariaDB database, a Python virtual environment, and a systemd
service. Run installation from a checkout separate from `/opt/prod/cmdb`.

## Prerequisites

The target machine needs Python 3.11 or later with virtual-environment support,
MariaDB server and client, and systemd. MariaDB must be running with root
administrative access through its local socket. Python dependencies are
downloaded during installation. On Debian/Ubuntu, the maintainer can prepare
the system with:

```sh
sudo apt install python3 python3-venv mariadb-server mariadb-client nmap
sudo systemctl enable --now mariadb
```

## Install

From the checkout:

```sh
sudo scripts/install.sh
```

The installer creates the `cmdb` Linux service account and the `cmdb` database
and database account. It generates `/etc/cmdb/database.env` owned by root with
mode `600`. Repeated installation reuses the credentials without resetting an
existing database password. An existing account with different credentials
causes installation to fail; it is not silently taken over.

Application files are copied to `/opt/prod/cmdb`, with Python dependencies in
`.venv`. The installer checks the database connection, installs
`cmdb-server.service`, enables it at boot, starts it, and checks `/health` and
`/ready`. Open `http://<server>:14444/` afterward.

The installer applies `schema/cmdb-schema-v1.sql` to the database. It creates the
`machines` table if absent, preserving existing rows on repeat installation.
`id` is the auto-increment primary key. `ipAddress` remains unique
(`VARCHAR(45)`, accommodating IPv4 and IPv6) for scan matching.
`macAddress` is nullable `VARCHAR(17)` and is also added to existing tables.
`hostName`, `site`, and `deployedComponent` are nullable `VARCHAR(255)` columns,
matching the `Machine` entity's attribute casing. `createdOn` and `updatedOn`
record insertion and the latest discovery update in UTC. The SQL file also adds
these timestamp columns to existing tables; old rows receive the migration time.
It assigns stable IDs to existing machines while preserving their records.
Edit the SQL file to maintain the schema.

`deployedComponents` stores each component's `pathname` and `machine` foreign key
to `machines.id`, with an internal auto-increment row ID. A machine can
contain zero or more component rows. The foreign key rejects components for
unknown machines and prevents deleting a machine while components reference it.
Changing a machine's IP address does not change its ID or component links.

## Upgrade

From the updated checkout:

```sh
sudo scripts/upgrade.sh
```

Upgrade reuses the installation process, preserving credentials and database
data. The service stops before dependencies and application files are updated.
A failure can leave it stopped; correct the reported issue and rerun the
command. Deployment does not provide automatic rollback.

## Uninstall

From the separate checkout:

```sh
sudo scripts/uninstall.sh
```

This stops and disables the service, drops the `cmdb` database (including all
inventory), and removes the service unit and `/opt/prod/cmdb`.
It retains `/etc/cmdb/database.env`, the MariaDB account and password, and the
Linux service account and group for reinstallation.

The checkout and system packages (including MariaDB and Nmap) remain installed.
Uninstall requires local MariaDB root access. It can be rerun from the checkout
after a partial uninstall and stops on errors. If dropping the database fails,
the service remains stopped and the application files remain in place.

## Runtime configuration

Paths, account names, and the default listener `0.0.0.0:14444` are defined in
`cmdb/constants/DCmdb.py`. The service is intended for a trusted LAN. It has no
authentication and installation does not add a public proxy or router mapping.

Systemd reads `/etc/cmdb/database.env` before starting the unprivileged process.
The file contains `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
Keep it private and out of this repository.

See [CMDB server]({{ site.baseurl }}{% link pages/server.md %}) for endpoints,
status commands, and development startup.
