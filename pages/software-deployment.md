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
| ModelElement | Auto-increment `id`; optional `namespace`; inherited `taggedValue` collection |
| TaggedValue | Technical `id`; `tag`, `value`, optional `modelElement` reference |
| Namespace | Shared `id` referencing ModelElement; `ownedElement` is the inverse of `ModelElement.namespace` |
| SoftwareSystem | Shared Namespace identity; `type`, `subtype`, `supplier`, `version` |
| Component | Shared Namespace identity; inherited `namespace` identifies its owning SoftwareSystem when present; `deployment` is the inverse of `DeployedComponent.component` |
| DeployedComponent | Shared Namespace identity; `pathname`, required `machine` and `component` references |
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

Only ModelElement and Namespace are needed from the core hierarchy to store
this ownership. Intermediate core classes with no currently needed fields
(such as Classifier, Package, and Subsystem) remain omitted; the Python entities
inherit from their nearest implemented ancestor, Namespace. No inherited
`name` or other unused parent attribute is copied onto a child.
There is no DeployedSoftwareSystem entity or association table in this subset.

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
IDs. OS details are stored for reporting; this change adds no OS controls or
presentation to the GUI.

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
