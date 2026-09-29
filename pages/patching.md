---
title: Debian Patching
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## Patch Now

Patching lists machines whose root operating system is identified as Debian by
inventory. Generic Linux fingerprints and Debian derivatives are excluded.
Patch Now queues a job and shows progress beside that host. Status appears in a separate column beside Patch Now. Schedules are optional and start disabled. The Status cell shows the latest patch or schedule message. New messages replace
it immediately. Unchanged job polls do not overwrite newer schedule messages;
historical completed results remain in Patch Report. Active jobs still show progress
when the page loads.

The independent `cmdb-patch.service` runs `cmdb-patch.py` using the application
venv and database configuration. The web service only queues work and reads status.
One worker processes jobs sequentially; pending jobs persist across restarts.
Repeated clicks for a machine with an active job return the same job.

Uptime starts as `---` and refreshes automatically when Patching opens. Refresh
Uptime at the bottom left also reads `/proc/uptime`
through the existing SSH interface and displays days, hours, and minutes. Hosts
that cannot be reached show Unavailable. Values are snapshots, preserved during
job polling but not stored in the database or refreshed by those polls.

## Scheduling

Each host has Enabled and a 20-character-wide Cron Schedule text box. Enter five
standard cron fields: minute, hour, day-of-month, month, and day-of-week.
Ranges, lists, steps, and month/weekday names are accepted; shortcuts such as
`@reboot` are not. For example, `0 12 * * 0` queues a patch on Sundays at noon
in the server's local time. The field can hold expressions longer than its visible
width. No schedule is enabled by default; backend validation reports invalid entries.


Update saves the settings and creates or replaces that host's service-account
cron entry. Clearing Enabled and pressing Update removes the entry while retaining
its settings and job history. Invalid expressions are rejected before any writes.
A cron write failure rolls the database edit back. Pending edits remain intact
while job status refreshes. Patch Now is independent of Enabled.

Cron calls the installed venv with `cmdb-patch.py --schedule-id <id>`. That mode
loads its own database configuration, rechecks Enabled, queues the same job as
Patch Now, and exits. Missing or disabled schedules do nothing. It does not
contact the web service. The independent patch worker still owns execution and
bookkeeping; jobs run sequentially, so cron specifies queue time, not a guaranteed
patch start time. Standard cron day matching and missed-run behavior apply.
Uninstall removes CMDB patch and backup cron entries while retaining unrelated jobs.

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
packages, without changing Debian releases. The runner then runs
`apt-get -y autoremove` to remove automatically installed packages that are no
longer needed, including old kernels eligible for removal, before the audit and
reboot. An autoremove failure stops the job before rebooting.
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
