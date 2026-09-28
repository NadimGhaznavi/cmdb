---
title: Software Deployment Model
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## OS inventory

The model uses the needed subset of
[CWM 1.1 SoftwareDeployment, section 5.7](https://www.omg.org/spec/CWM/1.1/PDF/).
Each entity maps to its own table. IDs are database identity keys; references
use those IDs rather than IP addresses.

| Entity | Table | Stored attributes and relationships |
| --- | --- | --- |
| SoftwareSystem | `softwareSystems` | `type`, `subtype`, `supplier`, `version` |
| Component | `components` | Identity; `deployment` is the inverse of `DeployedComponent.component` |
| DeployedSoftwareSystem | `deployedSoftwareSystems` | Required `softwareSystem` reference; `deployedComponent` association |
| DeployedComponent | `deployedComponents` | `pathname`, required `machine` and `component` references; `deployedSoftwareSystem` association |
| Machine | `machines` | `deployedComponent` is the collection of deployed component IDs referencing the machine |

The `deployedSoftwareSystemComponents` association table connects deployed
systems and components, with zero or more at both ends as specified by CWM.
One Component can have multiple deployments, each on exactly one Machine.
One DeployedSoftwareSystem refers to exactly one SoftwareSystem.

Core parent classes are omitted because their attributes are not currently
needed for storage. No inherited `name`, `namespace`, or other parent attribute
is copied onto these entities. Component currently needs only an identity for
the deployment reference. We do not yet store product-level ownership of
Components; adopting that relationship will require its owning core classes.

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
each machine gets its own DeployedSoftwareSystem and DeployedComponent.
Repeat scans reuse those records. A changed classification updates that
machine's deployment without changing another machine's software definition.
Unused definitions are retained.

The API returns `Machine.deployedComponent` as a list of deployed component
IDs. OS details are stored for reporting; this change adds no OS controls or
presentation to the GUI.

## Reporting

This query follows the stored relationships from a machine to its OS:

```sql
SELECT m.id, m.ipAddress, m.hostName, dc.pathname,
       ss.type, ss.subtype, ss.supplier, ss.version
FROM machines AS m
JOIN deployedComponents AS dc ON dc.machine = m.id
JOIN deployedSoftwareSystemComponents AS link ON link.deployedComponent = dc.id
JOIN deployedSoftwareSystems AS ds ON ds.id = link.deployedSoftwareSystem
JOIN softwareSystems AS ss ON ss.id = ds.softwareSystem
WHERE ss.type = 'OS';
```
