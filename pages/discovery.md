---
title: Discovery
---

[CMDB server]({{ site.baseurl }}{% link pages/server.md %})

Discovery is the last navigation link, to the right of Backups. Its Network
Discovery panel shows the configured network, Enabled, Cron Schedule, Update,
and Scan Now. Opening any page only reads stored inventory and settings;
the web worker starts no discovery scans at startup or on an internal timer.
Existing network, single-machine, and application scan buttons remain available.

Check Enabled, enter a five-field cron expression, and click Update to schedule
network scans. The initial policy is disabled; its suggested expression is
`*/5 * * * *` (every five minutes). Times follow the server's local timezone.
Uncheck Enabled and click Update to remove the cron job while keeping the policy.
A cron write failure rolls back the database edit; retry Update to reconcile it.
The network comes from `DCMDB.SCAN_TARGET`, currently `192.168.0.0/24`.

Scan Now queues a full inventory scan on the web worker regardless of whether
the schedule is enabled or saved. The button shows progress, reports failures,
and reloads stored data after completion.

## Independent cron execution

The Cron interface preserves unrelated, backup, and patch jobs. Discovery uses
one application policy in `DiscoverySchedule`, outside the CWM inventory model,
with the exact cron comment `cmdb-discovery-schedule-1`:

```text
*/5 * * * * /opt/prod/cmdb/.venv/bin/python -B /opt/prod/cmdb/cmdb-discovery.py --schedule-id 1 # cmdb-discovery-schedule-1
```

The installed runner loads `/etc/cmdb/database.env` and the saved policy. Missing
or disabled policies exit successfully without scanning. An enabled policy runs
the shared InventoryCoordinator collection and persistence workflow, including
network discovery, OS detection, host details, MariaDB, registered applications,
and final pruning. The runner exits 0 on success and 1 on failure, logging errors.
It does not contact or require the web service. The installer deploys the runner
and creates the schedule table through the install schema.

Scan IDs, web Status Messages, and reachability colors belong to the web worker's
memory. Independent cron scans update stored inventory; reload Inventory to see
those updates. Cron scan messages and reachability results are not transferred
into the web worker.
