---
title: Software Deployment Model
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## OS inventory

The model uses the needed subset of
[CWM 1.1 SoftwareDeployment, section 5.7](https://www.omg.org/spec/CWM/1.1/PDF/).
Each entity maps to its own table. IDs are database identity keys; references
use those IDs rather than IP addresses.

| Entity and table | Stored attributes and relationships |
| --- | --- |
| ModelElement | Auto-increment `id`; `name`; optional `namespace`; inherited `taggedValue` collection |
| TaggedValue | Technical `id`; `tag`, `value`, optional `modelElement` reference |
| Namespace | Shared `id` referencing ModelElement; `ownedElement` is the inverse of `ModelElement.namespace` |
| Package | Shared Namespace identity; target of `DataManager.dataPackage` |
| SoftwareSystem | Shared Package identity; `type`, `subtype`, `supplier`, `version` |
| Component | Shared Namespace identity; inherited `namespace` identifies its owning SoftwareSystem when present; `deployment` is the inverse of `DeployedComponent.component` |
| DeployedComponent | Shared Package identity; `pathname`, required `machine` and `component` references |
| DataManager | Shared DeployedComponent identity; `dataPackage` references through DataManagerDataPackage |
| Schema | Shared Package identity; database name inherited from ModelElement |
| Machine | Shared Namespace identity; `deployedComponent` is the collection of deployments referencing the machine |

The stored path is `SoftwareSystem → Component → DeployedComponent → Machine`.
A SoftwareSystem owns zero or more Components; a Component has zero or one
owning namespace. A Component has zero or more deployments, each referencing
exactly one Component and exactly one Machine.

Ownership is stored on `ModelElement.namespace`, with a foreign key to
`Namespace.id`. `Namespace.ownedElement` is derived by reading that inverse
relationship. Both fields stay on their owning parent classes. Each adopted
subclass shares its parent's ID through foreign keys. The scanner assigns a
Component's namespace to its SoftwareSystem and a DeployedComponent's namespace
to its Machine.

ModelElement, Namespace, and Package supply the adopted core hierarchy.
Intermediate classes with no currently needed fields, such as Classifier and
Subsystem, remain omitted; entities inherit from their nearest implemented
ancestor. The newly needed `name` attribute stays on ModelElement.
There is no DeployedSoftwareSystem entity or association table in this subset.

The database-inventory schema is prepared for a deployed MariaDB DataManager
linked to relational Schema objects through `DataManagerDataPackage`. This
increment does not yet discover or populate those records. DataProvider describes
client software, rather than the MariaDB server itself. See
[Schema Notes]({{ site.baseurl }}{% link pages/schema-notes.md %}) for association
multiplicities and naming decisions.

## Discovery mapping

Nmap's structured OS classification supplies:

| SoftwareSystem attribute | Value |
| --- | --- |
| `type` | `OS` |
| `subtype` | Nmap `osfamily` |
| `supplier` | Nmap `vendor`, or null if absent |
| `version` | Nmap `osgen`, or null if absent |

The scanner accepts a classification only when Nmap reports 100% accuracy and
all classifications at that accuracy agree on these fields. Approximate,
conflicting, and missing classifications leave the stored OS unchanged.
This is a fingerprint result, not a verified product release. Generation
strings such as `6.X` are retained as reported; distribution names and exact
versions are not inferred from the freeform fingerprint description.

The scanner represents the OS deployment using `pathname="/"`, our current
modeling convention. Nmap does not inspect the remote filesystem or verify
that path. Identical OS classifications share a SoftwareSystem and Component;
each machine gets its own DeployedComponent.
Repeat scans reuse those records. A changed classification updates that
machine's deployment without changing another machine's software definition.
Unused definitions are retained.

After the Nmap passes, hostname collection also reads the host's Linux
`os-release` file through the SSH interface (directly for the local machine).
The host-reported release replaces the Nmap classification for that machine's
existing `/` deployment when available:

| SoftwareSystem attribute | Host-reported value |
| --- | --- |
| `type` | `linux` |
| `subtype` | `ID` (required), e.g. `debian` |
| `supplier` | `Debian` when `ID=debian`; otherwise `VENDOR_NAME`, or null if absent |
| `version` | For Debian, `DEBIAN_VERSION_FULL`, falling back to `VERSION_ID`; otherwise `VERSION_ID` |

`VERSION_CODENAME` is stored as a TaggedValue on the SoftwareSystem, through
its inherited ModelElement identity: `tag="VERSION_CODENAME"`, `value="trixie"`.
The relationship is declared on ModelElement, not duplicated on SoftwareSystem.
Only the needed TaggedValue attributes are adopted; its unused Stereotype
relationship and attribute-free Element parent remain omitted.

Use `/etc/os-release` when present, otherwise `/usr/lib/os-release`. Do not
infer suppliers for other distributions or substitute a kernel version for
the product release. Hosts without readable, valid release data retain the
current observation, including any classification collected by Nmap in that
scan. Each scan runs Nmap first and host-reported collection afterward.

The API returns `Machine.deployedComponent` as a list of deployed component
IDs. The same response includes a `softwareDeployments` display projection,
joining DeployedComponent through Component's owning ModelElement to SoftwareSystem
and its codename tag. This projection adds no entity or schema attributes.
The graph draws a rounded software rectangle inside its containing machine,
labelled from subtype, optional codename, and version, e.g. `Debian (trixie) 13.6`.

## Reporting

This query follows the stored relationships from a machine to its OS:

```sql
SELECT m.id, m.ipAddress, m.hostName, dc.pathname,
       ss.type, ss.subtype, ss.supplier, ss.version
FROM Machine AS m
JOIN DeployedComponent AS dc ON dc.machine = m.id
JOIN Component AS c ON c.id = dc.component
JOIN ModelElement AS me ON me.id = c.id
JOIN SoftwareSystem AS ss ON ss.id = me.namespace
WHERE ss.type IN ('OS', 'linux');
```
