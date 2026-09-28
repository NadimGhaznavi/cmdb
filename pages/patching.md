---
title: Debian Patching
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## Patch Now

Patching lists machines whose root operating system is identified as Debian by
inventory. Generic Linux fingerprints and Debian derivatives are excluded.
Patch Now queues a job and shows progress beside that host. Status appears in a separate column beside Patch Now. There is no patch schedule. Reopening the page loads the last recorded job status.

The independent `cmdb-patch.service` runs `cmdb-patch.py` using the application
venv and database configuration. The web service only queues work and reads status.
One worker processes jobs sequentially; pending jobs persist across restarts.
Repeated clicks for a machine with an active job return the same job.

Uptime starts as `---`. Refresh Uptime at the bottom left reads `/proc/uptime`
through the existing SSH interface and displays days, hours, and minutes. Hosts
that cannot be reached show Unavailable. Values are snapshots, preserved during
job polling but not stored in the database or refreshed automatically.

## Patch Report

The separate Patch Report panel shows the most recent 100 jobs, newest first,
including queued, running, successful, and failed jobs. Columns show Patch Time
(browser-local time), Machine, Elapsed Time (`HH:MM:SS`), Status, and Details.
Patch Time uses the start time, or queue time before execution begins. Elapsed
time covers execution through reboot verification and is blank until completion.
Details show any error. Apt output is not stored. The report refreshes when
the page opens and with active job polling.

## Execution and constraints

The runner records the original boot ID, applies updates, records reboot pending,
requests a reboot, and verifies the new boot before recording success.
Every successful update run reboots, including when no packages changed.
Apt failures stop the job before rebooting.

Updates use `apt-get update` with repository errors treated as failures, followed
by `apt-get --with-new-pkgs upgrade`. This allows new dependencies, including kernel
packages, without removing installed packages or changing Debian releases.
Held packages remain held. Debian's noninteractive configuration keeps existing
modified configuration files when dpkg cannot choose a default. See the
[apt-get reference](https://manpages.debian.org/bookworm/apt/apt-get.8.en.html) and
[Debian's automatic upgrade guidance](https://www.debian.org/doc/manuals/debian-handbook/sect.automatic-upgrades.en.html).

Reboots are requested with a one-minute delay so bookkeeping can finish. Verification
allows 15 minutes for a new boot ID, then requires systemd's state to be `running`,
an empty `dpkg --audit`, and a successful `apt-get check`. A degraded system fails
verification, including when a service was already failing before patching.
These are host/package health checks, not application-specific health checks.

The runner stores job stages, timestamps, and errors.
Elapsed time can be derived from the start and completion timestamps.
If Neuromancer reboots, the runner service starts at boot and resumes the recorded
reboot verification without applying updates again. An interruption during apt
instead records a failure requiring inspection before retrying; no automatic
repair or rollback is attempted.

Remote operations use the existing administrative SSH key as root. Local operations
use a root-owned helper with sudo permission restricted to four fixed actions.
The helper confirms Debian on the target before any action. It must be installed
through the normal installer; never make the installed helper writable by `cmdb`.

## Operation

Run the normal installer/upgrade to create job storage, install the helper,
and enable the independent worker. Do not stop or upgrade the runner during an
active apt operation. Inspect worker errors with:

```sh
systemctl status cmdb-patch.service
journalctl -u cmdb-patch.service
```
