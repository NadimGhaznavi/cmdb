---
title: Activity / Interface / Entity Classification
lang: en
locale: en-US
language_name: English
translation_key: bmforge-classification
---

BMForge adopts an **Activity / Interface / Entity** classification inspired by the *Unified Software Development Process* (USDP). It uses the familiar separation of control, boundary, and entity responsibilities, with the names and conventions used in the existing applications. The goal is a readable design, not a framework.

**Classify each substantial application class by what it owns**, then put it in the corresponding application-owned package:

| Classification | Location | Responsibility | Example |
| --- | --- | --- | --- |
| **Activity** | `<app>/activity/` | Coordinates a use case, transforms data, and makes application decisions | `CollectVisit`, `PublishStatus` |
| **Interface** | `<app>/interface/` | Communicates with an external system **or abstracts that communication in domain terms** | `DbMgr`, `VisitorDb`, `MiningDb`, Git publisher, GeoIP client |
| **Entity** | `<app>/entity/` | Holds domain data and results, without persistence or transport responsibilities | `Visit`, `ExperimentStatus` |

The classification is by **responsibility**, not whether a Python class happens to declare methods. These are not Python abstract base classes and do not call for inheritance, automatic registration, a container, or an object-relational mapper.

## Data flow and dependency boundaries

For a database-backed activity:

```text
HTTP / ZeroMQ / CLI boundary
          |
          v
  activity/CollectVisit.py          operates on entity/Visit.py
          |
          v
  interface/VisitorDb.py            named domain operations and SQL
          |
          v
  interface/DbMgr.py                connection, cursor, transaction
          |
          v
         MariaDB
```

- **Activities** orchestrate domain work and call **named methods** on interfaces. They do not create cursors, issue SQL, or render themselves as data containers.
- **Domain interfaces** such as `VisitorDb` or `MiningDb` own table names, SQL, query parameters, mappings and transaction boundaries for their domain. They receive the generic `DbMgr` **by composition**. Add as many focused domain interfaces as the application needs, all using the same generic manager.
- **Technical interfaces** such as `DbMgr` own the driver mechanics. They have **no knowledge** of visits, mining, simulations or application schema.
- **Entities** hold values passed among activities and interfaces. They do not open database connections, run SQL, publish files or call remote services.

An application's `server/`, `zmq/`, `constants/`, and `scripts/` packages may still exist for their stated duties. Don't move transport entry points arbitrarily merely to satisfy a directory rule. Classify classes by their **actual responsibility**; keep one substantial class per module, with small local helpers where useful.

## Applying classification

For a new use case, identify its entities and activity, select the technical interfaces it needs, and create a domain interface only when persistence or another application-level boundary warrants one. The activity talks to `VisitorDb.record(visit)`, not to `DbMgr.execute(...)`. `VisitorDb` calls `DbMgr`; it must not open its own PyMySQL connection.

For shared patterns, copy the relevant **BMForge-owned template** into the destination application. Do not import another project's runtime modules. Do not clone the reference application's business logic. Choose project-specific names, constants and SQL outside the generic component.

### Pinned examples

The following *frozen* MyCount files, copied at commit `90574cd838ba43499a825c6a193b43cbc485c91c`, illustrate the roles:

| Example | Classification | Why |
| --- | --- | --- |
| `components/reference/mycount/mycount/activity/CollectVisit.py` | Activity | Coordinates preparation, enrichment and persistence |
| `components/reference/mycount/mycount/interface/VisitDb.py` | Interface, domain DAL | Owns visit SQL and calls its injected `DbMgr` |
| `components/reference/mycount/mycount/entity/Visit.py` | Entity | Holds the data that moves between layers |

These files have MyCount-specific imports and **are not generic drop-in modules**. The current canonical database template is `components/templates/db-server/interface/DbMgr.py`, specified in [DB Server]({{ site.baseurl }}{% link pages/component-db-server.md %}). The snapshots show the responsibility boundaries, not a requirement to copy MyCount.

## Codex acceptance criteria

1. Identify and preserve the responsibility classification of new and modified substantial classes.
2. Put business orchestration in `activity/`, domain/technology bridges in `interface/`, and domain data in `entity/`. Do not add empty packages for unused responsibilities.
3. Use dependency injection by ordinary constructors and composition. Do not invent a base-class hierarchy or dependency-injection framework.
4. Domain database classes use only the selected `DbMgr` for SQL execution and transaction mechanics. Activity/entity classes do not import `pymysql`.
5. Keep CMDB `BMFORGE_COMPONENT` provenance metadata **separate** from this class-role classification. The latter is evident from the responsibility and source package; no separate runtime classifier is required.

---

[DB Server]({{ site.baseurl }}{% link pages/component-db-server.md %}) · [Back to BMForge]({{ site.baseurl }}{% link index.md %})
