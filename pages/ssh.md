---
title: SSH Interface
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

`cmdb/interface/SSH.py` wraps the system OpenSSH client for remote commands.
It defaults to the FreeIPA-managed remote user `cmdbagent`, using the local service account's private key generated
by the [installer]({{ site.baseurl }}{% link pages/installation.md %}). It does
not use the database credentials or require a Python SSH package.

```python
from cmdb.interface.SSH import SSH

# Example host; SSSD must supply the IPA account and its authorized public key.
result = SSH().run("192.168.1.10", "uname -a")
print(result.stdout)
```

The `user` argument selects the remote login account. The client runs as local
`cmdb`; host administration logs in as `cmdbagent` and uses `sudo -n`.
FreeIPA owns the agent identity, authorized public key, host access, and sudo
privileges. Hosts use SSSD to resolve the user and supply SSH keys and sudo rules.

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
3. If that login fails, leave SSH inventory for this host until the next scan.
   A changed host key records `SSHHostKeyChanged="true"` on the machine and
   reports the failure in Status Messages. Inventory displays a muted amber
   border and a warning in machine details. A successful login clears the tag;
   other failures and offline scans preserve it.
4. Retrieve the hostname as `cmdbagent` with `hostname -f`, falling back to `hostname`,
   and update the Machine record by its stable ID.
5. Read `ip -j address show`, match the scanned IP to its interface, and store
   that interface's MAC address. This requires `iproute2` on the target. An
   unavailable command or missing MAC preserves the stored MAC and does not
   discard a successfully retrieved hostname.
6. Read `/etc/os-release`, falling back to `/usr/lib/os-release` when absent,
   and update the existing OS deployment at `/`. Release contents are parsed
   as data, never executed. Missing, invalid, or unreadable release data leaves
   the current OS observation unchanged and does not discard hostname or MAC data.

For the local machine, skip the port check and SSH connections.
The SSH interface executes the same hostname, MAC, and OS commands locally as `cmdbagent`.

Every connection uses the persistent local `cmdb` known-hosts file. New host keys are
automatically recorded before authentication; changed host keys are rejected.
The private key stays on the CMDB server. The public key is stored on the IPA user.
Discovery does not create or modify Linux accounts, home directories, or SSH keys.

Closed ports, denied logins, invalid hostname output, and
SSH timeouts leave the existing hostname unchanged and allow checks on other
machines to continue. Successful hostname retrieval replaces the stored value,
including a manual edit. Failures are retried on the next scan; host-key
changes are reported without exposing raw SSH output.

The activity uses `DCMDB.SSH_CONNECT_TIMEOUT_SECONDS` (5 seconds) and
`SSH_COMMAND_TIMEOUT_SECONDS` (30 seconds per command). It checks for shutdown
between hosts and commands. SSH follow-up still runs when the OS scan times out
or finds no usable OS classification. No database connection is held while
waiting for SSH.

## Reinstalled hosts and SSH trust

Inventory connects to a machine's scanned IP address. The IPA setup tool checks
both the enrolled hostname and its resolved IPv4 addresses. A successful login
using the hostname alone does not verify an existing IP entry in
`/var/lib/cmdb/.ssh/known_hosts`.

After reinstalling a host, compare its replacement host key through a trusted
console or authenticated Kerberos SSH session. For example, on that host:

```sh
cat /etc/ssh/ssh_host_ed25519_key.pub
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Once verified, an administrator can replace only the affected IP entry on the
CMDB server. This example uses a documentation address and a placeholder for
the verified public key's base64 field:

```sh
sudo -u cmdb ssh-keygen -F 192.0.2.7 -f /var/lib/cmdb/.ssh/known_hosts
sudo -u cmdb ssh-keygen -R 192.0.2.7 -f /var/lib/cmdb/.ssh/known_hosts
printf '%s\n' '192.0.2.7 ssh-ed25519 VERIFIED_BASE64_PUBLIC_KEY' |
  sudo -u cmdb tee -a /var/lib/cmdb/.ssh/known_hosts > /dev/null
```

Re-Scan that machine afterward. Successful SSH access clears the warning and
refreshes its hostname, MAC address, and OS release. Fedora's `ID=fedora` and
`VERSION_ID` populate the existing Linux OS deployment; an empty codename and
absent vendor remain unset. CMDB never automatically replaces a changed host
key or disables host-key checking.

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
tests the database agent identity and grants. When setup is needed, it runs
the MariaDB client as root through `cmdbagent`'s noninteractive sudo access,
verifies that the local server is MariaDB, applies `schema/cmdbagent.sql`, and
retests as `cmdbagent`. Root must have administrative MariaDB socket access.

Install and upgrade require the IPA identity to resolve, apply the same SQL
locally as root, and verify database access under that identity. Local discovery
uses the same agent sudo access as remote discovery. For an absent or unavailable MariaDB server,
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
