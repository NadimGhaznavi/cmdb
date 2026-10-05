---
title: SSH Interface
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

`cmdb/interface/SSH.py` wraps the system OpenSSH client for remote commands.
It defaults to remote user `cmdbagent`, using the local service account's private key generated
by the [installer]({{ site.baseurl }}{% link pages/installation.md %}). It does
not use the database credentials or require a Python SSH package.

```python
from cmdb.interface.SSH import SSH

# Example host; its remote cmdbagent account must already authorize the public key.
result = SSH().run("192.168.1.10", "uname -a")
print(result.stdout)

# Direct root login uses the same local cmdb key.
result = SSH().run("192.168.1.10", "id -u", user="root")
```

The `user` argument selects the remote login account. Direct root login requires
the remote root account to authorize the public key and its SSH server to permit
root key authentication. Local sudo permissions are not required: the client
still runs as local `cmdb`. Remote account configuration remains outside the
installer's scope.

Run the calling process as the local `cmdb` account so it can read the private
key. Defaults are port `22`, connection timeout `10` seconds, and overall
timeout `30` seconds; override them with `port`, `connect_timeout`, and
`timeout`. Optional `input` supplies text to the remote command's standard input.
The command string is interpreted by the remote shell, so quote
dynamic arguments appropriately.

`SSH.is_local()` recognizes local addresses by resolving the target and checking
whether a socket can bind to its address, without running an external command.
For a local target, `run()` executes the command through `/bin/sh` directly,
with the same input, output, timeout, and exit-status handling. When the requested identity differs from the process, it uses
`sudo -n -H -u cmdbagent -- /bin/sh -c ...`. The installed rule permits the
local `cmdb` service to execute commands as `cmdbagent`, not as root. Other
local identity switches are rejected. Local commands need no SSH server, key, or known-host entry.

The result is a `subprocess.CompletedProcess` containing text stdout and stderr.
A nonzero exit raises `subprocess.CalledProcessError` with the captured output;
a timeout raises `subprocess.TimeoutExpired`. Timing out stops the local SSH
client and does not guarantee termination of the remote command.

Connections use batch mode with the specified key and no SSH agent or client
configuration file. Password prompts are disabled. With OpenSSH's
[`StrictHostKeyChecking=accept-new`](https://man.openbsd.org/ssh_config#StrictHostKeyChecking),
new host keys are recorded automatically; changed host keys are rejected.

## Scanner follow-up

After Nmap discovery and OS scanning, `InventoryCoordinator` uses
`cmdb/activity/sources/HostSource.py` to check each discovered machine in turn:

1. Check whether TCP port 22 accepts a connection.
2. Test a login as `cmdbagent` using `true`.
3. If that login fails, try root using the same local key and run the account
   provisioning script. Root must already authorize this key and permit SSH.
4. After provisioning, test `cmdbagent` login again.
5. Retrieve the hostname as `cmdbagent` with `hostname -f`, falling back to `hostname`,
   and update the Machine record by its stable ID.
6. Read `ip -j address show`, match the scanned IP to its interface, and store
   that interface's MAC address. This requires `iproute2` on the target. An
   unavailable command or missing MAC preserves the stored MAC and does not
   discard a successfully retrieved hostname.
7. Read `/etc/os-release`, falling back to `/usr/lib/os-release` when absent,
   and update the existing OS deployment at `/`. Release contents are parsed
   as data, never executed. Missing, invalid, or unreadable release data leaves
   the current OS observation unchanged and does not discard hostname or MAC data.

For the local machine, skip the port check, SSH connections, and provisioning.
The SSH interface executes the same hostname, MAC, and OS commands locally as `cmdbagent`.

Every connection uses the persistent local `cmdb` known-hosts file, including
the initial login, root provisioning, and the `cmdbagent` retest. New host keys are
automatically recorded before authentication; changed host keys are rejected.
The private key stays on the CMDB server; only the public key is installed remotely.

The provisioning script targets Linux hosts with `getent`, `useradd`, and
`usermod`. It creates `cmdbagent` with a home and `/bin/sh` when absent. For an
existing service account it supplies a home if missing or set to `/nonexistent`,
and replaces a `nologin` or `false` shell with `/bin/sh`. A locked password field
is replaced with an unusable `*NP*` value to allow key authentication without
enabling password login. Existing usable password hashes are preserved.

The public key is appended to the remote account's `.ssh/authorized_keys`
only when absent, preserving other keys. The directory and file are owned by
`cmdbagent` with modes `700` and `600`. Repeated provisioning is safe. No remote
sudo permissions or SSH daemon settings are added.

Closed ports, denied logins, failed provisioning, invalid hostname output, and
SSH timeouts leave the existing hostname unchanged and allow checks on other
machines to continue. Successful hostname retrieval replaces the stored value,
including a manual edit. Failures are retried on the next scan without new logging.

The activity uses `DCMDB.SSH_CONNECT_TIMEOUT_SECONDS` (5 seconds) and
`SSH_COMMAND_TIMEOUT_SECONDS` (30 seconds per command). It checks for shutdown
between hosts and commands. SSH follow-up still runs when the OS scan times out
or finds no usable OS classification. No database connection is held while
waiting for SSH.


## Account transition

The local `cmdb` service account retains `/var/lib/cmdb`, its private key, and
known-hosts file. Install/upgrade creates a separate local `cmdbagent` account
with `/var/lib/cmdbagent` as its home, and authorizes the same public key.
Remote agents use their own home directories, normally `/home/cmdbagent`.
Existing remote `cmdb` accounts are not renamed or removed by the scanner.

For the one-time transition, run these commands from the development checkout:

```sh
sudo scripts/upgrade.sh
sudo /opt/prod/cmdb/.venv/bin/python -B scripts/cleanup-remote-cmdb.py
```

The cleanup reads machine addresses from the inventory, closes its database
connection, then runs as local `cmdb` to use the existing SSH identity. It logs
in as root remotely and runs `userdel --remove cmdb`, deleting the legacy account
and its home directory. Remote root must still authorize the CMDB key.
Local addresses are skipped, and a remote machine-ID check also rejects the
CMDB server reached through an alias. Unexpected home paths and symlinked homes
are rejected; supported legacy homes are `/home/cmdb` and `/var/lib/cmdb`.
Busy accounts are not forcibly killed. Failures are reported per host with a
nonzero final exit status; successful removals are safe to retry.

The next scan provisions `cmdbagent` where needed. The Linux-account cleanup does not remove database accounts.


## MariaDB agent account

`cmdb/interface/SSHDb.py` provisions `'cmdbagent'@'localhost'` for database
inventory. It uses MariaDB's
[unix_socket authentication](https://mariadb.com/docs/server/reference/plugins/authentication-plugins/authentication-plugin-unix-socket)
to authenticate the matching Linux identity, with no database password.
Commands run through SSH as `cmdbagent` and connect to the host's default local
MariaDB socket. TCP database access is not required.
These client commands explicitly use `--protocol=socket --skip-ssl` to avoid
TLS certificate checks on the local socket. Remote commands remain transported
over SSH.

After successful host inventory, the scanner checks for the MariaDB client and
tests the database agent identity and grants. When setup is needed on a remote
host, it connects as root using the existing SSH key, verifies that the local
server is MariaDB, applies `schema/cmdbagent.sql`, and retests as `cmdbagent`.
This also handles hosts whose Linux agent account already existed. Remote
root must have local administrative MariaDB socket access.

Install and upgrade apply the same SQL locally as root after creating the Linux
agent, then verify database access under that Linux identity. Runtime local
checks do not attempt root access. For an absent or unavailable MariaDB server,
failed administrative access, or failed agent verification, remote discovery
retains the machine information and retries on the next scan.

The grants are `SHOW DATABASES`, `SELECT`, `SHOW VIEW`, `TRIGGER`, and `EVENT`,
supporting inventory and logical dumps including routines and events.
[MariaDB privileges](https://mariadb.com/docs/server/reference/sql-statements/account-management-sql-statements/grant)
apply globally so newly discovered user databases can be backed up too.
Provisioning is repeatable and does
not revoke additional grants. It sets the agent's authentication to `unix_socket`;
the application's existing `cmdb` database account is unaffected. SQL stays in
the external schema folder and is copied with the installed application.

After verification, `MariaDBSource` calls `SSHDb.inventory()` to read the server
version, data directory, and schema names using `schema/mariadb-inventory.sql`. The activity persists the
[MariaDB inventory]({{ site.baseurl }}{% link pages/software-deployment.md %}#mariadb-discovery)
through DataManagerDb after completing the remote commands. `SSHDb.backup_db`
runs a manual dump on that same host; see
[manual backups]({{ site.baseurl }}{% link pages/backups.md %}).
