---
title: SSH Interface
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

`cmdb/interface/SSH.py` wraps the system OpenSSH client for remote commands.
It connects as `cmdb`, using the local service account's private key generated
by the [installer]({{ site.baseurl }}{% link pages/installation.md %}). It does
not use the database credentials or require a Python SSH package.

```python
from cmdb.interface.SSH import SSH

# Example host; its remote cmdb account must already authorize the public key.
result = SSH().run("192.168.1.10", "uname -a")
print(result.stdout)
```

Run the calling process as the local `cmdb` account so it can read the private
key. Defaults are port `22`, connection timeout `10` seconds, and overall
timeout `30` seconds; override them with `port`, `connect_timeout`, and
`timeout`. The command string is interpreted by the remote shell, so quote
dynamic arguments appropriately. No local shell is invoked.

The result is a `subprocess.CompletedProcess` containing text stdout and stderr.
A nonzero exit raises `subprocess.CalledProcessError` with the captured output;
a timeout raises `subprocess.TimeoutExpired`. Timing out stops the local SSH
client and does not guarantee termination of the remote command.

Connections use batch mode with the specified key and no SSH agent or client
configuration file. Password prompts are disabled. With OpenSSH's
[`StrictHostKeyChecking=accept-new`](https://man.openbsd.org/ssh_config#StrictHostKeyChecking),
new host keys are recorded automatically; changed host keys are rejected.

Paths are defined in `DCmdb`. The interface does not create remote accounts,
copy keys to hosts, or run automatically as part of machine scanning.
