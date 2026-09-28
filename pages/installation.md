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
sudo apt install python3 python3-venv mariadb-server mariadb-client nmap sudo openssh-client cron
sudo systemctl enable --now mariadb
```

## Install

From the checkout:

```sh
sudo scripts/install.sh
```

The installer creates the `cmdb` Linux service account and the `cmdb` database
and database account. It generates `/etc/cmdb/database.env` owned by root with
group `cmdb` and mode `640`, so the standalone cron runner can read it. Existing
root-only mode `600` files are adjusted on installation or upgrade. Repeated
installation reuses the credentials without resetting an
existing database password. An existing account with different credentials
causes installation to fail; it is not silently taken over.

The local `cmdb` account uses `/var/lib/cmdb` as its home, retaining its
`nologin` shell. The installer generates an Ed25519 SSH key without a passphrase
for unattended outbound connections:

- Private key: `/var/lib/cmdb/.ssh/id_ed25519` (mode `600`).
- Public key: `/var/lib/cmdb/.ssh/id_ed25519.pub` (mode `644`).
- Known hosts: `/var/lib/cmdb/.ssh/known_hosts` (mode `600`).

These files belong to `cmdb`; `.ssh` has mode `700`. Reinstallation reuses the
private key and known hosts. A missing public key is reconstructed from the
private key. An invalid or encrypted existing private key causes installation
to fail without replacing it. The service can write its SSH directory under
the otherwise read-only system filesystem configuration.

Remote accounts and public-key authorization are not configured by the installer.
The scanner's SSH follow-up can provision remote `cmdb` access when root already
accepts this public key.
The same key supports remote `cmdbagent` or root login when authorized by the remote
account. Selecting remote root in the SSH interface requires no additional local
sudoers rule or separate key.
See [SSH interface]({{ site.baseurl }}{% link pages/ssh.md %}) for usage.

Installation and upgrade validate and install `/etc/sudoers.d/cmdb-nmap`, owned
by root with mode `0440`, containing:

```sudoers
cmdb ALL=(root) NOPASSWD: /usr/bin/nmap
cmdb ALL=(cmdbagent) NOPASSWD: /bin/sh
```

This grants the `cmdb` user passwordless root access to Nmap with unrestricted
arguments. The Nmap interface uses python-nmap's `sudo=True` option, with the
executable fixed to `/usr/bin/nmap`. The service sets `NoNewPrivileges=false`
to allow sudo; the Python server itself continues to run as `cmdb`.

Application files are copied to `/opt/prod/cmdb`, with Python dependencies in
`.venv`, including `python-crontab`. It also copies `cmdb-backup.py` and enables
the system cron service. The CMDB service can update its own crontab through
the standard `crontab` helper; its sandbox permits writes to
`/var/spool/cron/crontabs`. The installer checks the database connection, installs
`cmdb-server.service`, enables it at boot, starts it, and checks `/health` and
`/ready`. Open `http://<server>:14444/` afterward.

The installer applies `schema/cmdb-schema-v1.sql` to the database. It creates the
`Machine` table if absent, preserving existing rows on repeat installation.
`id` is the shared primary key inherited from Namespace and ModelElement;
ModelElement allocates the auto-increment identity. `ipAddress` remains unique
(`VARCHAR(45)`, accommodating IPv4 and IPv6) for scan matching.
`macAddress` is nullable `VARCHAR(17)`.
`hostName` and `site` are nullable `VARCHAR(255)` columns,
matching the `Machine` entity's attribute casing. `createdOn` and `updatedOn`
record insertion and the latest discovery update in UTC.
Edit the SQL file to maintain the fresh-install schema. During initial
development, it does not migrate existing tables. After a schema change, use
uninstall/install to recreate the database and let discovery populate it.

`DeployedComponent` stores each deployment's `pathname`, `machine` foreign key
to `Machine.id`, and required `component` reference to `Component.id`, with an
identity shared with its Namespace and ModelElement parent records. A machine can
contain zero or more component rows. The foreign key rejects components for
unknown machines and prevents deleting a machine while components reference it.
Changing a machine's IP address does not change its ID or component links.
`SoftwareSystem` owns `Component` through `ModelElement.namespace` and the
inverse `Namespace.ownedElement` relationship. These tables hold the
[OS software deployment model]({{ site.baseurl }}{% link pages/software-deployment.md %}).
`Machine.deployedComponent` is derived from the foreign-key relationship rather
than stored as a text column on `Machine`.

## Upgrade

From the updated checkout:

```sh
sudo scripts/upgrade.sh
```

Upgrade reuses the installation process, preserving credentials and database
data when the schema is unchanged. For schema changes at this stage, use
`scripts/uninstall.sh` followed by `scripts/install.sh` instead.
The service stops before dependencies and application files are updated.
A failure can leave it stopped; correct the reported issue and rerun the
command. Deployment does not provide automatic rollback.

## Uninstall

From the separate checkout:

```sh
sudo scripts/uninstall.sh
```

This stops and disables the service, removes CMDB-owned backup cron entries
while preserving unrelated entries, drops the `cmdb` database (including all
inventory), and removes the service unit, `/opt/prod/cmdb`, and the Nmap sudoers rule.
It retains `/etc/cmdb/database.env`, the MariaDB account and password, and the
Linux service account and group for reinstallation. `/var/lib/cmdb`, including
the SSH key and known-hosts file, is retained too.

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


## Inventory account

Install and upgrade retain the `cmdb` service identity and SSH key, and provision
local `cmdbagent` with home `/var/lib/cmdbagent`. The sudo rule also permits
`cmdb` to execute local inventory commands as `cmdbagent`. Remote discovery
uses `cmdbagent` with the existing key. See the
[one-time remote account cleanup]({{ site.baseurl }}{% link pages/ssh.md %}#account-transition)
for removing the old remote `cmdb` accounts and homes after upgrade.
Uninstall retains both local accounts and their homes.


The installer also provisions MariaDB's `cmdbagent@localhost` using socket
authentication and grants `SHOW DATABASES`, `SELECT`, `SHOW VIEW`, `TRIGGER`,
and `EVENT` for inventory and dumps. It verifies access as Linux
`cmdbagent`. This runs on upgrade as well as fresh installation and uses
`schema/cmdbagent.sql`. The existing application database credentials are retained.

For manual backups, each database host needs `mariadb-dump`, `flock`,
and the standard coreutils commands. The configured backup directory may use
autofs/NFS or local storage, and `cmdbagent` must be able to create files there.
The installer does not configure mounts or NFS permissions. The service grants
write access to the configured backup directory for local neuromancer dumps.
See [manual backups]({{ site.baseurl }}{% link pages/backups.md %}).
