---
title: Manual Backups
---

[CMDB server]({{ site.baseurl }}{% link pages/server.md %})

Expand a host on Backups and click Backup Now beside a user database. This action
does not depend on Enabled or a saved schedule. Scheduling, Update, and retention
deletion are not implemented.

## Execution

BackupManager records an attempt and queues it on a single worker. Duplicate
requests for the same active model item return the same attempt ID. Each worker
opens its own CMDB connection for bookkeeping, closing it before remote work.
SSHDb runs `mariadb-dump` as `cmdbagent` on the database host, using the local
MariaDB socket. Neuromancer uses the existing local command path without SSH.

`DCmdb.BACKUP_DIR` is `/imports/backups`. The output location is:

```text
/imports/backups/<host>/db/mariadb-<host>-<database>-<UTC timestamp>-<attempt ID>.dump
```

The host is the short inventory hostname, falling back to its IP. Unsafe filename
characters are percent-encoded. The database part is limited to 80 encoded
characters. UTC start timestamps include seconds and microseconds to distinguish
attempts. The record stores the relative pathname, size, and SHA-256 checksum.

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
On first backup access after server restart, unfinished records are marked failed
with an unknown-outcome message. If completion cannot be saved, the manager logs
the error and blocks another request for that item until restart.

Mirroring is provided by the storage system outside CMDB. Existing dump files
are never overwritten or removed by this workflow.
