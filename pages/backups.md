---
title: Backups
---

[CMDB server]({{ site.baseurl }}{% link pages/server.md %})

Expand a host on Backups and click Backup Now beside a user database. This action
does not depend on Enabled or a saved schedule. To schedule a database, check
Enabled, choose Retention, and click Update. Daily backups run at noon in the
CMDB server's local time. Uncheck Enabled and click Update to remove its cron job.
Retention is saved as policy only; automatic file deletion is not implemented.

## Cron scheduling

The Cron interface uses [python-crontab](https://pypi.org/project/python-crontab/)
to manage the `cmdb` account's crontab. Each entry has an exact comment marker,
`cmdb-backup-schedule-<id>`. Updates replace only that schedule's entry; unrelated
cron jobs are preserved. The configured expression is `DCmdb.BACKUP_CRON`,
currently `0 12 * * *`.

Cron invokes the installed venv directly:

```text
0 12 * * * /opt/prod/cmdb/.venv/bin/python -B /opt/prod/cmdb/cmdb-backup.py --schedule-id 12 # cmdb-backup-schedule-12
```

The runner reads `/etc/cmdb/database.env`, loads the policy, and calls the shared
BackupManager and SSHDb code to execute one backup and record its outcome. It
does not contact or require the web service. A missing or disabled schedule is
a successful no-op. Success exits 0; dump, permission, configuration, and tool
errors exit 1. Backup attempts store the error when database access is available.
Cron handles process timing; there is no application scheduling loop.

Update saves Enabled, Daily frequency, and Retention, then writes the cron entry.
A cron write failure rolls back the database edit and reports an error. If an
update fails, retry it to reconcile the settings and cron entry. Deleting a policy
through `DELETE /api/backup-schedules/<id>` removes its cron entry and preserves
backup history. Disabling via the UI retains the policy with Enabled cleared.

## Backups page

The title box reads CMDB Backups, with both words at the same heading size.
The Inventory view similarly reads CMDB Inventory.
Live Databases and Backup Vault have their own bordered panels below it.
Backup Vault lists all recorded successful database backups,
newest completion first (newest record first when times match). Its columns are
Backup Time (`YYYY-MM-DD HH:MM:SS` in browser-local time), Elapsed Time (`HH:MM:SS`), Machine (short hostname
or IP address), Database, and Filename (the full path formed from `DCmdb.BACKUP_DIR`
and the backup record's relative pathname).
Elapsed Time measures whole seconds from CMDB's attempt creation to completion,
including queue time, preparation, dumping, and checksum calculation. Hours do
not wrap at 24. While a job is starting or running, its progress message is
“Processing backup job...”.
The table refreshes when the view opens and after an observed backup completes.
It uses backup records and current inventory names; it does not scan the filesystem
or verify that recorded files still exist. Failed and running attempts are excluded.

## Execution

Backup Now records an attempt and queues it on the web service's worker. Duplicate
manual requests for the same active model item return the same attempt ID.
The cron runner executes synchronously in its own process. Both use BackupManager
for bookkeeping and close their CMDB connections before remote work.
SSHDb runs `mariadb-dump` as `cmdbagent` on the database host, using the local
MariaDB socket. Neuromancer uses the existing local command path without SSH.

`DCmdb.BACKUP_DIR` is `/imports/disk1/backups`. The output location is:

```text
/imports/disk1/backups/<host>/db/mariadb-<host>-<database>-YYYY-MM-DD_HH:MM:SS.dump
```

The host is the short inventory hostname, falling back to its IP. Unsafe filename
characters are percent-encoded. The database part is limited to 80 encoded
characters. Filenames use the UTC start date and time to the second, without
fractional seconds or an attempt-ID suffix. An existing filename is never
overwritten. The record stores the relative pathname, size, and SHA-256 checksum.

The host first accesses the base directory, triggering autofs where configured.
Local storage is also supported, including the backing directory on Wintermute,
the NFS server. No filesystem-type check is performed.
It creates its temporary file in the destination host's `db` directory,
dumps directly there, then computes the size and checksum on that host. It
publishes the completed file with a hard link and removes the temporary name,
without copying the file across filesystems or through the CMDB server.
Files use mode 600. A shared-filesystem lock prevents concurrent dumps of the
same database, including a remote command surviving a CMDB restart.

The dump includes database creation statements, data, views, triggers, routines,
and events. `--single-transaction --quick` provides a consistent InnoDB snapshot;
nontransactional tables and concurrent schema changes require additional care.
See [mariadb-dump](https://mariadb.com/docs/server/clients-and-utilities/backup-restore-and-import-clients/mariadb-dump).

## Prerequisites and outcomes

Every database host must provide the backup directory and allow `cmdbagent` to
write to it. For NFS mounts, ownership and permissions must work with the NFS
server's UID/GID mapping. Installation does not change NFS configuration.
Install/upgrade grants the local agent database dump privileges. Remote agents
with old grants are reprovisioned through the existing root SSH path.

The host-side command is limited to `DCmdb.BACKUP_TIMEOUT_SECONDS` (3600 seconds).
Normal failures clean up temporary files and record the error. A force kill or
storage outage can leave a `.part` file. A lost connection may leave file outcome
unknown; CMDB does not infer success without returned metadata.

The page polls the record while the backup runs. Success updates Last Backup in
browser-local time. Failure displays the recorded error and preserves the last
successful timestamp. Reloading the view reconnects to the latest attempt.
Restarting or viewing the web service does not modify running attempts, which may
belong to independent cron processes. Interrupted jobs are not automatically
recovered or retried. If completion cannot be saved, the manager logs the error;
the standalone runner exits unsuccessfully.

Mirroring is provided by the storage system outside CMDB. Existing dump files
are never overwritten or removed by this workflow.
