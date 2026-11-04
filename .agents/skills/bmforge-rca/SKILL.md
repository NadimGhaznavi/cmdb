---
name: bmforge-rca
description: Investigate deployed application bugs by gathering production logs and database dumps over read-only SSH, then reproducing and fixing the issue locally. Use for remote production troubleshooting.
---

# Remote production root cause analysis

**Production is an evidence source, never a debugging workspace.** Codex works on the development workstation (e.g. Sally), not the deployed server (e.g. Wintermute).

1. SSH only to an authorized host. Inspect the deployed version, service status, and relevant log and database locations, just enough to identify useful evidence.
2. Collect only what is needed. Stream journal output and database dumps to a **local** scratch directory; copy existing remote log files if useful. Never stage dumps, scripts, or temporary files on the server.
3. Leave the remote host. Restore the database or inspect the collected data on the workstation. Reproduce, investigate, edit, and test **locally**.
4. Keep deployment separate: a fix goes through the normal release/upgrade process, not RCA.

**Never modify a remote host during RCA.** No ad-hoc SQL on production, including investigative `SELECT` queries; dump and query locally instead. No remote file changes, Git mutations, service restarts, migrations, package installs, or debugging scripts. If an operation cannot be done read-only, stop that approach and explain why.

For example, with authorized access and configured database credentials:

~~~sh
set -o pipefail
work=$(mktemp -d)
ssh HOST 'journalctl -u SERVICE --no-pager -n 500' > "$work/service.log"
ssh HOST 'mariadb-dump --single-transaction --quick --skip-lock-tables DBNAME' \
    | gzip > "$work/database.sql.gz"
~~~

The scratch directory is on the workstation. Keep the collection narrow, and never commit production logs, database dumps, or credentials. Do not create incident reports or other process artifacts unless requested.
