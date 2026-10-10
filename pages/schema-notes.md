---
title: Schema Notes
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

This page records non-obvious database constraints and implementation decisions.

## Backup schedules

`BackupSchedule` is an application-specific entity, outside CWM, with its own
auto-increment ID. Its required, unique `modelElement` foreign key references
`ModelElement.id`, allowing one policy per inventory item: a database Catalog
today or a DeployedComponent later. It does not inherit from ModelElement.

| Column | Type | Default / constraint |
| --- | --- | --- |
| `id` | BIGINT UNSIGNED | Auto-increment primary key |
| `modelElement` | BIGINT UNSIGNED | Required, unique reference to ModelElement |
| `enabled` | BOOLEAN | False; restricted to 0 or 1 |
| `frequency` | VARCHAR(16) | `daily`; only supported value |
| `retention` | VARCHAR(16) | `1-week`; also accepts `2-weeks`, `1-month`, `forever` |

All columns are non-null. Deleting a referenced ModelElement is blocked until
its schedule is explicitly removed. Inventory discovery does not create schedule
rows. Update saves policy values and manages the corresponding service-account
cron entry. Daily execution is at noon in server-local time; retention is stored
but not yet enforced. Manual execution is available through Backup Now.
The table is included in the install schema; no record migration is added.

## Backup attempts

`Backup` is an application entity with its own ID and a required reference to
`ModelElement.id`. Multiple attempts may reference the same item. There is no
dependency on BackupSchedule, so manual attempts need no schedule and changing
or removing a schedule preserves history. Referenced inventory items cannot be
deleted while backup records remain.

| Column | Purpose |
| --- | --- |
| `id` | Auto-increment primary key |
| `modelElement` | Required foreign key to the item backed up |
| `startedOn` | Required UTC start time, stored as DATETIME(6) |
| `completedOn` | UTC completion time; null while running |
| `status` | `running` (default), `succeeded`, or `failed` |
| `pathname` | File path relative to the backup base directory; nullable until known |
| `sizeBytes` | Unsigned completed file size; null until successful |
| `checksum` | SHA-256 of the completed file, 64 lowercase hexadecimal characters; null until successful |
| `error` | Failure details; null otherwise |

Completed attempts require a completion time no earlier than their start.
Success requires a nonempty pathname, size, checksum, and no error. Running and
failed attempts have no completed-file size or checksum. The latest-success
index supports looking up Last Backup by model item and completion time.
BackupManager creates attempts and records SSHDb results. Backup Now polls those
records and displays the latest successful completion time. See
[manual backups]({{ site.baseurl }}{% link pages/backups.md %}) for execution and failure handling.

## Data packages and inherited names

Database names are stored in `ModelElement.name`, inherited by relational
`Catalog`. Names use a binary collation to preserve case distinctions, and are
not globally unique: different server instances can host the same database name.
The column is nullable for existing object kinds whose names are not collected.

`Package` now has a shared-identity table because it is the declared target of
`DataManager.dataPackage` and the parent of Catalog. DeployedComponent also
inherits Package; SoftwareSystem uses Package as its nearest implemented
ancestor. Existing OS writes create the required Package rows.

`DataManagerDataPackage` stores the CWM association of that exact name. Its
`dataManager` and `dataPackage` columns reference DataManager and Package,
respectively, and together form its primary key. Both ends remain many-valued.
This is an association table, not a new entity class or a replacement for
namespace ownership. A package can exist without links, and a manager can
have no packages. Duplicate links and dangling references are rejected.

DataManager shares its DeployedComponent ID; Catalog shares its Package ID.
No attributes are copied down to either child. Catalog and unneeded attributes such as `isCaseSensitive` are deferred.

## Deployment owner consistency

`DeployedComponent.machine` and its inherited `ModelElement.namespace` must
identify the same Machine. The database enforces this with:

```sql
FOREIGN KEY (id, machine) REFERENCES ModelElement (id, namespace)
```

The supporting unique index on `ModelElement(id, namespace)` allows the pair
to be referenced. The separate foreign key from `DeployedComponent.machine`
to `Machine.id` ensures that the owner is a Machine.

Both deployment key columns are required. A deployment therefore cannot use a
parent with a null owner. Inserts or updates that make the references disagree
are rejected, including direct SQL changes to either table. Other model
elements may still have a null namespace.

Create the parent with its machine namespace before inserting the deployment.
Foreign keys are checked immediately; changing only one ownership reference
is rejected even inside a transaction. The scanner already writes the matching
values in this order.

This constraint is part of the fresh-install schema. Apply it through the
current uninstall/install workflow; no record migration is provided.


## Tagged values and OS definitions

`TaggedValue.modelElement` references the owning ModelElement. The unique key
`(modelElement, tag)` enforces CWM's one-value-per-tag rule for an attached tag.
Tag names use a binary collation so their casing is significant. TaggedValue
has its own technical ID; it does not inherit from ModelElement.

Machine classification uses `tag="DeploymentEnvironment"` with `value="dev"`,
`"qa"`, or `"prod"`. Its `modelElement` references the machine's inherited
ModelElement identity (the same ID as Machine and Namespace). Update creates
the tag or changes its value while preserving its ID. Unclassified removes
only this tag; other tags and other machines' classifications are preserved.
No additional schema column or table is required.

The scanner includes `VERSION_CODENAME` in software-definition matching. Hosts
with matching release fields and codenames share the same definition and tag.
A changed codename selects or creates a separate definition rather than changing
one already used by other machines. Missing codename data is not invented.
The scanner recognizes both Nmap's `OS` classification and host-reported `linux`
as OS deployments at `/`, so successive observations update the same deployment.


## Discovered database identity

MariaDB instances are matched by Machine ID and reported data-directory path.
Catalog names are scoped through ModelElement.namespace to that DataManager;
DataManagerDataPackage separately records the access relationship. This keeps
names on their inherited owner and preserves the association's many-to-many
structure. Discovery writes are serialized by the existing scanner worker.
A version change reuses the deployed instance and catalogs while selecting a
new SoftwareSystem/Component definition. Missing catalogs are retained for now.

## Application database clients

DataProvider shares its DataManager and DeployedComponent identity.
ProviderConnection shares a ModelElement identity, with its namespace equal to
its required `dataProvider` owner. Its required `dataManager` reference identifies
the server, and a check constraint prohibits connecting a provider to itself.
DeployedComponentsUsage stores the many-valued application/client deployment
relationship using the CWM end names `usingComponents` and `usedComponents`.
Database names discovered from MariaDB are now stored as relational Catalogs;
Schema remains a separate adopted class for future schema detail. These changes
apply to fresh installations, following the model mapping policy.
