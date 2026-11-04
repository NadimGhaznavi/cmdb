---
title: DB Server Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.db-server"
spec_version: "0.5.0"
spec_status: "draft"
translation_key: bmforge-component-db-server
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

This contract follows the [engineering policy]({{ site.baseurl }}{% link pages/engineering-contract.md %}), [health check contract]({{ site.baseurl }}{% link pages/health-checks.md %}), and [traceability rules]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

## Intent and scope

Provide a minimal application-owned database service layer backed by MariaDB using PyMySQL. This is application-side data access, not a managed MariaDB daemon. Separate connection/SQL execution mechanics from application schema and queries. Do not introduce an ORM, global connection pool, migration framework or remote service without a concrete requirement.

## Approved runtime modules

This is the **complete approved module inventory for the canonical, reusable `DbMgr.py`** in specification `0.5.0`.

| Origin | Module | Purpose |
| --- | --- | --- |
| Python stdlib | `contextlib` | `contextmanager` for transaction commit and rollback |
| Third-party | `pymysql` | MariaDB connection, bound SQL, queries, and transactions |
| Third-party submodule | `pymysql.cursors` | `DictCursor` for dictionary result rows (part of PyMySQL, not another package) |

**Approval boundary:** The canonical `DbMgr.py` is **copied unchanged** into each application using MariaDB; its methods, imports and class name are not customized. Supply application configuration at construction, and create separate `*Db` domain interface classes for application SQL. Codex **must pause and ask the user** before adding, removing, or replacing an approved infrastructure module or changing `DbMgr.py`. User-approved changes belong in a revised BMForge specification before adoption.

These are Python import modules, not a complete transitive dependency tree. The consuming application's dependency file records installed package versions. Application business logic and separately selected BMForge components are outside this list; they must not quietly change this component's technology choices.

**Database technology:** MariaDB. Do not substitute PostgreSQL, SQLite, SQLAlchemy, Peewee, mysql-connector, an ORM, an alternate driver, or an application-external database service. A different database backend is a new component specification requiring user approval.

**Not part of the generic manager:** `GeoIpDb`, `VisitDb`, `MiningDb`, `GeoIpSource`, schema definitions, and application-specific SQL. They belong in the consuming application's **domain interface** classes. See [Activity / Interface / Entity Classification]({{ site.baseurl }}{% link pages/classification.md %}).

## Canonical implementation and layered DAL

**Every new MariaDB-backed application copies the same file, unchanged:**
`components/templates/db-server/interface/DbMgr.py` → `<app>/interface/DbMgr.py`.

The application's configuration interface resolves secrets, connection details and timeouts and passes them as constructor keyword arguments. **Do not import application constants, schema or environment readers inside the canonical manager.** It has generic `execute`, `insert`, `execute_many`, `query`, `transaction(read_only=False)`, `health`, and `close` methods, plus context-managed cleanup.

Above `DbMgr`, the app defines one or more **domain database interface classes**, such as `VisitorDb`, `MiningDb`, or `GeoIpDb`. Each takes a `DbMgr` instance through its constructor. They own SQL, schema, row-to-entity translation, and grouped writes. They never call `pymysql.connect` or manage cursors directly. Multiple domain classes may share a single `DbMgr` within one owning worker/transaction, **not across threads**. Database provisioning and business data migrations remain separate operations.

For example, a consumer may implement:

```python
class VisitorDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def count(self):
        return self._db.query("SELECT COUNT(*) AS visits FROM page_views")[0]["visits"]
```

An `activity/CollectVisit.py` class calls named `VisitorDb` operations and works on an `entity/Visit.py` value. No SQL lives in activities, entities, templates or HTTP/ZeroMQ transport. This arrangement uses plain composition, not inheritance or an ORM. See the [classification contract]({{ site.baseurl }}{% link pages/classification.md %}).

**New project integration:** copy `DbMgr.py` unchanged, pass the resolved configuration, write only the required domain `*Db` interfaces and entities, and test the application transaction and health paths. Existing applications do not require an automatic migration merely because this draft specification has changed.

## Character set and collation standard

Use **`CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`** for application databases, tables and their ordinary character columns, and the same charset/collation for every application connection. Collation controls text comparison and sorting; it is separate from the storage engine or SQL column type. This pins the setting that previously differed between SnakeLab's `run_id` (`utf8mb4_unicode_ci`) and Ax3l's `process_id` (`utf8mb4_uca1400_ai_ci`), breaking cross-database text comparisons.

Name **both** settings explicitly when provisioning databases and creating tables; do not inherit version-dependent MariaDB server or charset defaults. Character columns may inherit the explicitly pinned table default. Any column-level charset/collation declaration must name the same pair; a different comparison policy requires an explicit approved specification change. Text identifiers compared across application databases must use this same collation on both sides, not a query-specific `COLLATE` workaround.

MariaDB's `JSON` alias has a type-defined `utf8mb4_bin` collation; preserve that semantic exception and identify it during schema audits rather than converting JSON payloads. Store shared textual identifiers in ordinary columns using the standard pair, not JSON payloads. Frozen source examples may have older or domain-specific collations; their DDL is not the current standard.

For example, in application-owned provisioning/schema code:

```sql
CREATE DATABASE example_app
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE example_app.records (
  record_id VARCHAR(64) NOT NULL PRIMARY KEY
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

The canonical manager pins PyMySQL's `charset="utf8mb4"` and `collation="utf8mb4_unicode_ci"`. A connection setting does **not** rewrite a database, table or existing text column. Provisioning and upgrades must inspect the effective settings in `information_schema.SCHEMATA`, `TABLES` and `COLUMNS`, and verify `@@character_set_connection` and `@@collation_connection` through the application's own connection. Merely changing a database default leaves existing tables and columns unchanged.

Existing applications retain their pinned implementation until an owner-approved upgrade. If adoption requires converting existing text, plan an explicit data migration and check indexes, uniqueness and foreign keys under the target comparison rules. Never automatically alter deployed databases or change the MariaDB server-wide defaults from `DbMgr`.

Upstream references: [MariaDB charset/collation settings](https://mariadb.com/docs/server/reference/data-types/string-data-types/character-sets/setting-character-sets-and-collations), [MariaDB JSON semantics](https://mariadb.com/docs/server/reference/data-types/string-data-types/json) and [PyMySQL connection options](https://pymysql.readthedocs.io/en/latest/modules/connections.html). These explain mechanics; BMForge pins the pair above rather than following upstream defaults.

## Reference snapshot

- `components/reference/bmgeoip/bmgeoip/interface/DbMgr.py`: historical version of the mechanics, **not** the copyable canonical file (it imports BMGeoIP constants)
- `components/reference/bmgeoip/bmgeoip/interface/DatabaseEnvironment.py`: BMGeoIP-specific configuration loading; new apps resolve their own settings separately
- `components/reference/bmgeoip/bmgeoip/interface/GeoIpDb.py`: application SQL and schema owned by a domain interface
- `components/reference/mycount/mycount/interface/VisitDb.py`: another domain interface using `DbMgr`, pinned from MyCount commit `90574cd838ba43499a825c6a193b43cbc485c91c`

## Required contract

- The **unchanged canonical `DbMgr.py`** owns one MariaDB connection, created from resolved application configuration and closed deterministically. The application provides its DB host/port or socket, schema name, credentials and timeouts when constructing it. Never share one manager instance between worker threads.
- Resolve and validate external connection configuration in an application interface **before** constructing `DbMgr`; do not add configuration-file parsing or application-specific constants to the manager. No credentials in source, public documentation, status messages or HTTP output.
- Use `utf8mb4` with `utf8mb4_unicode_ci` for schemas, tables, text columns and connections as specified above, dictionary results as needed, explicit connect/read/write timeouts, and strict SQL mode consistent with the reference implementation. Preserve the manager's UTC database session; local-time display belongs to the HTTP presentation contract.
- Use the canonical methods: parameterised `execute`, `insert` (generated ID), `execute_many`, `query`, `transaction(read_only=False)`, `health` and `close`. All SQL and dynamic identifier allowlists live in the application's `*Db` interfaces, not the manager. Use driver-bound parameters for data values.
- Transaction context commits only on success and rolls back on exceptions, preserving the original exception even when rollback also fails. DDL and schema creation are handled separately from multi-statement data transactions.
- The application's **interface/** domain `*Db` classes own SQL schema, indexes, constraints, read/write methods, row/entity mapping and atomic write workflows. `activity/` uses their named operations and `entity/` stores the data. **Never import GeoIpDb or create GeoIP tables** for an unrelated application.
- Offer a small application-internal, read-only health operation using the **application's configured database connection** (for example `SELECT 1` via its DB manager). It reports failure when the app cannot use that connection; do not catch and suppress errors, reconnect automatically, or create a special monitoring connection. The application's health handler reports this result to CMDB; **CMDB must not connect to MariaDB directly for DB Server health**.
- Use `CMDB_DATABASES` declarations for app discovery and follow BMForge runtime configuration and deployment guidance. An inventory declaration does not create database users, schema or backups automatically.
- Explicitly choose the consistency and concurrency contract for each application's writes. For a time-tracking service, consider idempotent event IDs and transactional session transitions only when those behaviours are part of its own requirements.

## Acceptance checks

1. Connect with a dedicated test database and credentials; missing/bad credentials fail without exposing passwords.
2. Bound insert/query round trip works, including Unicode and parameterised values; injection-like input is stored as a value.
3. Multiple writes commit atomically; an injected failure rolls all writes back and rethrows.
4. Separate worker threads use separately owned connections; closure releases resources.
5. Invalid/missing configuration and a database outage yield explicit errors and do not leave a partially reported success.
6. Application-internal DB health succeeds while the app can query through its own connection, fails on a simulated outage, and causes the application's aggregate `/health` to become unhealthy; no direct CMDB-to-MariaDB connection is used.
7. Only the new application's schema and SQL are present; no BMForge/bmgeoip runtime imports. Verify CMDB declarations agree with deployment.
8. Verify `<app>/interface/DbMgr.py` is an unchanged copy of `components/templates/db-server/interface/DbMgr.py`, with `BMFORGE_COMPONENT` version `0.5.0`. No application SQL, constants or domain names belong in the manager.
9. Verify each `*Db` domain interface delegates SQL execution and transactions to its injected `DbMgr`, while activities and entities have no direct PyMySQL access.
10. Verify the DB Server uses only approved modules and MariaDB; any infrastructure change must be approved by the user before updating this component specification.
11. On a dedicated MariaDB test instance, inspect effective database/table/ordinary-text-column charset and collation plus connection variables: all must match `utf8mb4` / `utf8mb4_unicode_ci`; account explicitly for JSON's type-defined exception above. Create two disposable application schemas with the standard, insert matching text identifiers, and verify a cross-database join succeeds without query-level `COLLATE` or casts. An upgrade check must detect a mismatched existing column even when its database default already matches; do not silently convert it.
