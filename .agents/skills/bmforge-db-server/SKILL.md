---
name: bmforge-db-server
description: Add MariaDB access to a Python application using BMForge's unchanged canonical DbMgr.py and application-owned domain *Db interfaces. Use for SQL storage, transactions and database-backed activities; never introduce an ORM.
---

# MariaDB DAL

Read `references/specification.md`, `references/classification.md`, `references/engineering-contract.md` and `references/health-checks.md`. **Do not modify the canonical manager.**

1. Copy `assets/DbMgr.py` **byte-for-byte** into `<app>/interface/DbMgr.py`. The marker is `bmforge.db-server` spec `0.5.0`. All consuming apps using this spec have the same generic file.
2. Resolve connection configuration outside the manager in the application, then inject those values. Do not insert application constants or configuration-file parsing into `DbMgr`.
3. Build only needed application-owned domain interfaces, such as `VisitorDb` or `MiningDb`, at `<app>/interface/<Name>Db.py`. Each composes a `DbMgr`, owns its own SQL and transactions, and never connects with PyMySQL independently.
4. Activities call named domain interface operations and entities carry records. SQL never goes in activities, entities, HTTP or ZMQ transport modules.
5. The health operation uses the application's configured connection, not a direct CMDB connection to MariaDB.
6. Inspect pinned examples `references/source/bmgeoip/.../GeoIpDb.py` and `references/source/mycount/.../VisitDb.py` only for the domain-interface pattern. Do not copy their schema or business logic.
7. Test parameters, transactions/rollback, per-worker resource lifetime and health. No ORM or alternative database driver without approval.
8. Pin `CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` explicitly in database and table DDL. Ordinary character columns inherit that table default or explicitly name the same pair; preserve MariaDB JSON's type-defined binary collation as specified. The canonical manager pins the connection too. Audit effective database/table/column and connection settings, and test a cross-database text join without `COLLATE` workarounds. Database defaults do not convert existing columns: adoption by an existing app requires a reviewed upgrade and any necessary explicit migration, never automatic production changes.
