---
title: Patching
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## Patch types

Patching lists machines whose root operating system is identified by inventory
as Debian or Fedora. Generic Linux fingerprints and derivatives are excluded.
Fedora targets must use DNF; image-based systems managed by rpm-ostree are not
supported by this package workflow.

Each host has two rows with independent settings and actions:

| Patch type | Packages | After patching |
| --- | --- | --- |
| Kernel | Installed kernel packages and dependencies needed for their updates | Reboot and verify host/package health |
| Other | Available updates with kernel packages excluded | Verify package health without requesting a reboot |

Patch Now queues the selected type and shows progress in that row's Status
column. It works independently of Enabled. Repeated clicks for an active job
of the same host and type return that job; the other type can be queued
separately. The independent `cmdb-patch.service` runs `cmdb-patch.py` using the
application venv and database configuration. One worker processes all queued
jobs sequentially, and pending jobs persist across restarts. The web service
only queues work and reads status.

New patch or schedule messages replace the row's Status immediately. Unchanged
job polls preserve newer schedule messages; historical completed results remain
in Patch Report. Active jobs still show progress when the page loads.

Uptime starts as `---` and refreshes automatically when Patching opens. Refresh
Uptime also reads `/proc/uptime` through SSH, once per host, and updates both
rows. Values use seconds below a minute, whole minutes below an hour, hours
below a day, and days thereafter. Hours and days use one decimal place.
Unreachable hosts show Unavailable. These snapshots survive job polling but
are not stored in the database.

## Scheduling

Each host and patch type has its own Enabled checkbox and 20-character-wide
Cron Schedule text box. Both schedules start disabled. Unsaved kernel schedules
prefill `0 13 * * 1` (Mondays at 1 p.m.); other schedules prefill `0 12 * * *`
(daily at noon). These times use the server's local timezone. Prefilling does
not save or enable a schedule. Saved expressions, including an empty field,
are preserved.

Enter five standard cron fields: minute, hour, day-of-month, month, and
day-of-week. Ranges, lists, steps, and month/weekday names are accepted;
shortcuts such as `@reboot` are not. The field can hold expressions longer
than its visible width. Backend validation rejects invalid entries before
writing anything.

Update saves only that row's settings and creates or replaces its service-account
cron entry. Clearing Enabled and pressing Update removes only that entry while
retaining its settings and job history. A cron write failure rolls back the
database edit. Pending edits in either row remain intact during job polling
and updates to the other row.

Cron calls the installed venv with `cmdb-patch.py --schedule-id <id>`. That mode
loads its own database configuration, rechecks Enabled, queues the schedule's
host and patch type, and exits without contacting the web service. Missing or
disabled schedules do nothing. Cron specifies queue time, not a guaranteed
patch start time; the independent worker still processes jobs sequentially.
Standard cron day matching and missed-run behavior apply. Uninstall removes
CMDB-owned cron entries while retaining unrelated jobs.

## Patch Report

Patch Report shows the most recent 100 jobs, newest first, including queued,
running, successful, and failed jobs. Columns show Patch Time (browser-local
time), Machine, Patch Type, Elapsed Time (`HH:MM:SS`), Status, and Details.
Patch Time uses the start time, or queue time before execution begins. Elapsed
time covers execution and, for kernel jobs, reboot verification; it is blank
until completion. Details show any error. Package-manager output is not stored.
The report refreshes when the page opens and with active job polling.

## Debian packages

Both types first run `apt-get update`, treating repository errors as failures.
Kernel jobs select installed `linux-image-*`, `linux-headers-*`,
`linux-modules-*`, `linux-kbuild-*`, and `linux-compiler-*` packages and use
`apt-get --only-upgrade --no-remove install`. Required dependencies, including
new versioned kernel images, may be installed. Keep the appropriate kernel
metapackage installed so new kernel ABI packages are selected automatically.

Other jobs use `apt-get --with-new-pkgs --no-remove upgrade`, with a temporary
negative APT pin for those kernel families. Existing administrator preferences
are retained and no persistent package holds are changed. Updates that require
an excluded kernel package stay back or fail dependency resolution rather than
installing it in this window. `linux-libc-dev` remains in other patching because
it provides userspace development headers.

Neither type runs a broad `autoremove`, which could remove packages outside
its scope. Old Debian kernels therefore require separate administrator cleanup.
The commands do not change Debian releases. Existing dpkg configuration files
are kept when dpkg cannot choose a default, and held packages are not overridden.
See the [APT command reference](https://manpages.debian.org/bookworm/apt/apt-get.8.en.html)
and [APT preferences](https://manpages.debian.org/bookworm/apt/apt_preferences.5.en.html).

## Fedora packages

Kernel jobs run `dnf -y --refresh upgrade 'kernel*'`. Other jobs run
`dnf -y --refresh --exclude='kernel*' upgrade`. The kernel family includes the
image, modules, development packages, and headers with that prefix. DNF resolves
necessary dependencies and applies its configured kernel retention policy.
The workflow uses the host's `dnf` command, including Fedora's DNF5 implementation,
and does not perform a Fedora release upgrade. See the
[DNF5 upgrade reference](https://dnf5.readthedocs.io/en/latest/commands/upgrade.8.html)
and [package exclusion option](https://dnf5.readthedocs.io/en/latest/dnf5.8.html).

## Verification and recovery

The runner records the original boot ID before patching. Package failures stop
the job before any reboot. Debian package verification requires an empty
`dpkg --audit` and a successful `apt-get check`; Fedora uses `dnf check`.

Other jobs finish after package verification without requesting a reboot.
Services may restart through their normal package scripts, and updates to
userspace components may still require a later administrator-managed reboot.

Every successful kernel update run requests a reboot, including when no packages
changed. Reboots use a one-minute delay so bookkeeping can finish. Verification
allows 15 minutes for a new boot ID, then requires systemd's state to be
`running` and package verification to pass. A degraded system fails verification,
including when a service was already failing before patching. These checks do
not verify application-specific health.

Job stages, timestamps, and errors are stored. If the CMDB host reboots, the
worker resumes recorded kernel reboot verification without applying updates
again. Interruption during either package operation records a failure requiring
inspection before retrying; no automatic repair or rollback is attempted.

Local and remote actions run as the FreeIPA-managed `cmdbagent` identity using
its noninteractive sudo privileges. Remote SSH uses the existing CMDB key.
The helper confirms Debian or Fedora on the target before any action.

## Operation

Installation enables the independent worker and installs its helper. This
change updates the fresh-schema definitions of `Patch` and `PatchSchedule`;
existing schemas are not migrated automatically, following CMDB's initial
development policy. Prepare a fresh schema before running this version against
an older database layout. Do not stop or upgrade the runner during an active
package operation. Inspect worker errors with:

```sh
systemctl status cmdb-patch.service
journalctl -u cmdb-patch.service
```
